import os
import re
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import discord
from discord import app_commands
from discord.ext import commands

# ==========================================
# ⚙️ CẤU HÌNH BOT TÀI CHÍNH
# ==========================================
MY_GUILD_ID = 1559384250279526562  # ID máy chủ của bạn
MY_BOT_TOKEN = "MTU1OTM4NTc0ODk1OTEzNzkzMg.Gj0azG.hg63y2Nq0sUs43np4ON3RwKoW_PTHIti9J0Lgs"
DB_NAME = "finance.db"
# ==========================================

VN_TZ = timezone(timedelta(hours=7))

def get_vn_now():
    return datetime.now(VN_TZ)

# Khởi tạo cơ sở dữ liệu SQLite
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            type TEXT,          -- 'CHI' hoặc 'THU'
            amount INTEGER,      -- Số tiền (VND)
            category TEXT,      -- Danh mục
            note TEXT,          -- Ghi chú
            created_at TEXT     -- Thời gian
        )
    """)
    conn.commit()
    conn.close()

init_db()

# Hàm chuyển đổi số tiền thông minh (50k -> 50000, 1.5tr -> 1500000)
def parse_money(input_str: str) -> int:
    s = input_str.strip().lower().replace(",", "").replace(".", "")
    if s.endswith("k"):
        val = float(s[:-1]) * 1000
    elif s.endswith("tr") or s.endswith("m"):
        val = float(s[:-2] if s.endswith("tr") else s[:-1]) * 1000000
    else:
        val = float(re.sub(r"[^\d]", "", s))
    return int(val)

def format_money(amount: int) -> str:
    return f"{amount:,.0f}".replace(",", ".") + " đ"

# 1. Web server ngầm giữ bot online 24/7
class PingServer(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Finance Bot OK")
    def log_message(self, *args):
        pass

def start_web():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), PingServer).serve_forever()

threading.Thread(target=start_web, daemon=True).start()

# 2. Khởi tạo Discord Bot
class FinanceBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

    async def setup_hook(self):
        guild = discord.Object(id=MY_GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

bot = FinanceBot()


# =======================================================
# 💸 LỆNH 1: GHI NHẬN CHI TIÊU (/chi)
# =======================================================
@bot.tree.command(name="chi", description="Ghi nhận một khoản chi tiêu")
@app_commands.describe(
    so_tien="Số tiền đã chi (VD: 45k, 150k, 2tr hoặc 45000)",
    danh_muc="Khoản mục chi tiêu",
    ghi_chu="Chi tiết món chi (VD: Ăn sáng, xăng xe, cuộn nhựa in 3D...)"
)
@app_commands.choices(danh_muc=[
    app_commands.Choice(name="🍜 Ăn uống", value="Ăn uống"),
    app_commands.Choice(name="⛽ Đi lại / Xăng xe", value="Đi lại"),
    app_commands.Choice(name="🛒 Mua sắm cá nhân", value="Mua sắm"),
    app_commands.Choice(name="⚙️ Đồ nghề / Dự án / Linh kiện", value="Dự án/Linh kiện"),
    app_commands.Choice(name="💡 Tiền nhà / Điện nước / Sinh hoạt", value="Sinh hoạt"),
    app_commands.Choice(name="💸 Khác", value="Khác")
])
async def cmd_chi(itx: discord.Interaction, so_tien: str, danh_muc: app_commands.Choice[str], ghi_chu: str):
    try:
        amount = parse_money(so_tien)
        if amount <= 0:
            await itx.response.send_message("⚠️ Số tiền phải lớn hơn 0!", ephemeral=True)
            return

        now_str = get_vn_now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO transactions (user_id, type, amount, category, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (itx.user.id, "CHI", amount, danh_muc.value, ghi_chu, now_str))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="🔴 ĐÃ GHI NHẬN CHI TIÊU",
            color=discord.Color.red()
        )
        embed.add_field(name="💰 Số tiền", value=f"**-{format_money(amount)}**", inline=True)
        embed.add_field(name="📂 Danh mục", value=danh_muc.name, inline=True)
        embed.add_field(name="📝 Nội dung", value=ghi_chu, inline=False)
        embed.set_footer(text=f"Thời gian: {get_vn_now().strftime('%d/%m/%Y - %H:%M')}")

        await itx.response.send_message(embed=embed)
    except Exception as e:
        await itx.response.send_message(f"⚠️ Lỗi định dạng số tiền: {e}", ephemeral=True)


# =======================================================
# 💵 LỆNH 2: GHI NHẬN THU NHẬP (/thu)
# =======================================================
@bot.tree.command(name="thu", description="Ghi nhận một khoản tiền nhận được")
@app_commands.describe(
    so_tien="Số tiền nhận được (VD: 500k, 10tr...)",
    nguon="Nguồn thu nhập",
    ghi_chu="Chi tiết nguồn tiền"
)
@app_commands.choices(nguon=[
    app_commands.Choice(name="💼 Lương tháng", value="Lương"),
    app_commands.Choice(name="🎁 Tiền thưởng / Phụ cấp", value="Thưởng"),
    app_commands.Choice(name="🛠️ Bán đồ / Dự án phụ", value="Dự án phụ"),
    app_commands.Choice(name="💵 Khác", value="Khác")
])
async def cmd_thu(itx: discord.Interaction, so_tien: str, nguon: app_commands.Choice[str], ghi_chu: str):
    try:
        amount = parse_money(so_tien)
        if amount <= 0:
            await itx.response.send_message("⚠️ Số tiền phải lớn hơn 0!", ephemeral=True)
            return

        now_str = get_vn_now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO transactions (user_id, type, amount, category, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                  (itx.user.id, "THU", amount, nguon.value, ghi_chu, now_str))
        conn.commit()
        conn.close()

        embed = discord.Embed(
            title="🟢 ĐÃ GHI NHẬN THU NHẬP",
            color=discord.Color.green()
        )
        embed.add_field(name="💰 Số tiền", value=f"**+{format_money(amount)}**", inline=True)
        embed.add_field(name="📂 Nguồn thu", value=nguon.name, inline=True)
        embed.add_field(name="📝 Nội dung", value=ghi_chu, inline=False)
        embed.set_footer(text=f"Thời gian: {get_vn_now().strftime('%d/%m/%Y - %H:%M')}")

        await itx.response.send_message(embed=embed)
    except Exception as e:
        await itx.response.send_message(f"⚠️ Lỗi định dạng số tiền: {e}", ephemeral=True)


# =======================================================
# 📊 LỆNH 3: BÁO CÁO THỐNG KÊ THÁNG (/thongke)
# =======================================================
@bot.tree.command(name="thongke", description="Xem tổng kết thu chi và số dư trong tháng hiện tại")
async def cmd_thongke(itx: discord.Interaction):
    now = get_vn_now()
    thang_hien_tai = now.strftime("%Y-%m")

    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()

    # Tổng thu trong tháng
    c.execute("SELECT SUM(amount) FROM transactions WHERE type='THU' AND strftime('%Y-%m', created_at)=?", (thang_hien_tai,))
    tong_thu = c.fetchone()[0] or 0

    # Tổng chi trong tháng
    c.execute("SELECT SUM(amount) FROM transactions WHERE type='CHI' AND strftime('%Y-%m', created_at)=?", (thang_hien_tai,))
    tong_chi = c.fetchone()[0] or 0

    # Thống kê chi theo từng danh mục
    c.execute("""
        SELECT category, SUM(amount) 
        FROM transactions 
        WHERE type='CHI' AND strftime('%Y-%m', created_at)=?
        GROUP BY category 
        ORDER BY SUM(amount) DESC
    """, (thang_hien_tai,))
    chi_tiet_chi = c.fetchall()
    conn.close()

    so_du = tong_thu - tong_chi

    embed = discord.Embed(
        title=f"📊 BÁO CÁO TÀI CHÍNH THÁNG {now.strftime('%m/%Y')}",
        color=discord.Color.blue()
    )
    embed.add_field(name="📥 Tổng thu", value=f"**+{format_money(tong_thu)}**", inline=True)
    embed.add_field(name="📤 Tổng chi", value=f"**-{format_money(tong_chi)}**", inline=True)
    embed.add_field(name="💰 Còn lại", value=f"**{format_money(so_du)}**", inline=True)

    if chi_tiet_chi:
        danh_sach_text = []
        for cat, val in chi_tiet_chi:
            phan_tram = (val / tong_chi * 100) if tong_chi > 0 else 0
            danh_sach_text.append(f"• **{cat}:** {format_money(val)} ({phan_tram:.1f}%)")
        embed.add_field(name="📉 Chi tiết các khoản chi", value="\n".join(danh_sach_text), inline=False)
    else:
        embed.add_field(name="📉 Chi tiết các khoản chi", value="Chưa có khoản chi nào trong tháng.", inline=False)

    embed.set_footer(text=f"Cập nhật lúc: {now.strftime('%H:%M %d/%m/%Y')}")
    await itx.response.send_message(embed=embed)


# =======================================================
# 💾 LỆNH 4: SAO LƯU DỮ LIỆU (/saoluu)
# =======================================================
@bot.tree.command(name="saoluu", description="Gửi file database để sao lưu về máy, không sợ mất dữ liệu")
async def cmd_saoluu(itx: discord.Interaction):
    if os.path.exists(DB_NAME):
        file = discord.File(DB_NAME, filename=f"finance_backup_{get_vn_now().strftime('%Y%m%d')}.db")
        await itx.response.send_message("📁 File sao lưu cơ sở dữ liệu của bạn đây:", file=file, ephemeral=True)
    else:
        await itx.response.send_message("⚠️ Chưa có dữ liệu phát sinh!", ephemeral=True)


@bot.event
async def on_ready():
    print(f"Bot Tai Chinh Online: {bot.user}")

bot.run(os.getenv("DISCORD_TOKEN") or MY_BOT_TOKEN)
