import asyncio
import logging
import os
import random
import string
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    KeyboardButton,
    ReplyKeyboardMarkup,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand,
    BotCommandScopeDefault,
    ChatPermissions,
)
from aiogram.exceptions import TelegramRetryAfter
from aiohttp import web

# --- CẤU HÌNH CƠ BẢN ---
TOKEN = os.getenv("BOT_TOKEN", "8905955749:AAGojrcwwf4tqe01Naog3k_fTjaLUayFliU")
ADMIN_ID = 8312903264
GROUP_CHAT_ID = None 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- FSM STATES ---
class NapMoneyState(StatesGroup):
    waiting_for_amount = State()

class SlotPGState(StatesGroup):
    waiting_for_spins = State()

# --- BIẾN TRẠNG THÁI TRÒ CHƠI & KHUYẾN MÃI ---
current_session = 105027
current_jackpot = 600000.0
recent_tai_xiu = ['🟢', '🔴', '🟢', '🔴', '🟢', '🔴', '🟢', '🔴', '🟢', '🔴', '🟢', '🔴']
recent_chan_le = ['🔵', '🟡', '🔵', '🟡', '🔵', '🟡', '🔵', '🟡', '🔵', '🟡', '🔵', '🟡']
game_running = True

promo_config = {"percent": 0.0, "expire_at": None}

# Biến bổ sung cho tính năng mới
force_result = None  # Cờ ép kết quả: 'tai' hoặc 'xiu'

# --- TRẠNG THÁI GAME MÁY BAY AVIATOR ---
aviator_user_turn = {}      # Lưu lượt cược của user (1 - 13)
aviator_history = {}        # Lưu lịch sử phiên chơi của user
aviator_active_games = {}   # Lưu thông tin phiên đang chạy của user

users_db = {
    ADMIN_ID: {
        "balance": 50000000.0, 
        "name": "Admin Tổng", 
        "total_nap": 10000000.0, 
        "total_cuoc": 5000000.0,
        "history_nap": [],
        "history_rut": [],
        "referrer_id": None,
        "invite_count": 0,
        "ref_commission": 0.0
    }
}
bets_current = {} 
active_codes = {} 

def get_user(user_id: int, name: str = "Thành viên", referrer_id: int = None):
    if user_id not in users_db:
        users_db[user_id] = {
            "balance": 200.0, 
            "name": name,
            "total_nap": 0.0,
            "total_cuoc": 0.0,
            "history_nap": [],
            "history_rut": [],
            "referrer_id": referrer_id,
            "invite_count": 0,
            "ref_commission": 0.0
        }
        if referrer_id and referrer_id != user_id:
            if referrer_id not in users_db:
                get_user(referrer_id)
            users_db[referrer_id]["invite_count"] += 1
    return users_db[user_id]

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Mở menu chính / Hướng dẫn"),
        BotCommand(command="sodu", description="Kiểm tra số dư ví"),
        BotCommand(command="nap", description="Nạp tiền tự động / QR Code"),
        BotCommand(command="rut", description="Tạo lệnh rút tiền"),
        BotCommand(command="code", description="Nhập Giftcode nhận thưởng"),
        BotCommand(command="lenh", description="Xem danh sách lệnh người chơi"),
    ]
    try:
        await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    except Exception as e:
        logging.error(f"Lỗi set commands: {e}")

# --- BÀN PHÍM CHÍNH (REPLY KEYBOARD) ---
main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="👤 Tài Khoản Của Tôi"), KeyboardButton(text="🎮 Danh Sách Game")],
        [KeyboardButton(text="💰 Số Dư"), KeyboardButton(text="💳 Nạp Tiền"), KeyboardButton(text="💸 Rút Tiền")],
        [KeyboardButton(text="🤝 Giới Thiệu"), KeyboardButton(text="🏆 Top Nạp"), KeyboardButton(text="🔥 Top Cược")],
        [KeyboardButton(text="📜 Lịch Sử Nạp"), KeyboardButton(text="📜 Lịch Sử Rút")],
        [KeyboardButton(text="🎁 Nhập Code"), KeyboardButton(text="🎧 CSKH")]
    ],
    resize_keyboard=True
)

# --- MENU INLINE DANH SÁCH GAME ---
def get_game_list_inline_kb():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Tài Xỉu 🎲", callback_data="game_tx"), InlineKeyboardButton(text="Chẵn Lẻ ⚫️", callback_data="game_cl")],
        [InlineKeyboardButton(text="Bỏng Ngô 🍿", callback_data="game_ngo"), InlineKeyboardButton(text="Bóng Rổ 🏀", callback_data="game_br")],
        [InlineKeyboardButton(text="Bóng Đá ⚽️", callback_data="game_bd"), InlineKeyboardButton(text="Bowling 🎳", callback_data="game_bw")],
        [InlineKeyboardButton(text="Phi Tiêu 🎯", callback_data="game_pt"), InlineKeyboardButton(text="Kéo Búa Bao 🖐️✌️👊", callback_data="game_kbb")],
        [InlineKeyboardButton(text="Quay Hũ PG 🎰", callback_data="game_slot_pg"), InlineKeyboardButton(text="Cứu Thương 🚑", callback_data="game_cuu_thuong")],
        [InlineKeyboardButton(text="Đèn Đỏ Đèn Xanh🚙", callback_data="game_den_do_den_xanh"), InlineKeyboardButton(text="Rót Rượu 🍷", callback_data="game_rot_ruou")],
        [InlineKeyboardButton(text="Bầu Cua 🦀", callback_data="game_bau_cua"), InlineKeyboardButton(text="Máy Bay Avitor 🛩️", callback_data="game_aviator")],
        [InlineKeyboardButton(text="❌ Đóng Menu", callback_data="game_close")]
    ])
    return keyboard

async def lock_chat(chat_id: int):
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(can_send_messages=False)
        )
    except Exception as e:
        logging.warning(f"Không thể khóa chat: {e}")

async def unlock_chat(chat_id: int):
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True,
                can_invite_users=True
            )
        )
    except Exception as e:
        logging.warning(f"Không thể mở khóa chat: {e}")

@dp.message(F.new_chat_members)
async def welcome_new_member(message: types.Message):
    for member in message.new_chat_members:
        if member.is_bot:
            continue
        user = get_user(member.id, member.full_name)
        username_text = f"@{member.username}" if member.username else member.full_name
        
        welcome_text = (
            f"🎉 <b>CHÀO MỪNG THÀNH VIÊN MỚI</b> 🎉\n\n"
            f"🆔 <b>ID:</b> <code>{member.id}</code>\n"
            f"👤 <b>Tên:</b> <b>{member.full_name}</b>\n"
            f"💰 <b>Số dư tân thủ:</b> <b>{user['balance']:,.0f} VND</b>\n\n"
            f"👑 <i>Chúc mừng đại gia <b>{username_text}</b> mới tham gia cổng game BTV88 Club! Chúc đại gia đại thắng!</i> 🚀"
        )
        await message.answer(welcome_text)

# --- LỆNH ADMIN MỚI VÀ CŨ ---
@dp.message(Command("checkid"))
async def cmd_admin_checkid(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    filtered_users = {uid: udata for uid, udata in users_db.items() if udata.get("balance", 0) > 5000}
    if not filtered_users:
        await message.reply("📋 Không có người chơi nào có số dư trên 5,000đ.")
        return
    text = f"📊 <b>THỐNG KÊ NGƯỜI CHƠI CÓ SỐ DƯ > 5,000đ ({len(filtered_users)} người):</b>\n\n"
    for uid, udata in filtered_users.items():
        text += f"• ID: <code>{uid}</code> - Tên: <b>{udata['name']}</b> - Số dư: <b>{udata['balance']:,.0f} VND</b>\n"
    await message.reply(text)

@dp.message(Command("kq"))
async def cmd_admin_kq(message: types.Message):
    global force_result
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠️ Cú pháp: <code>/kq tai</code> hoặc <code>/kq xiu</code>")
        return
    choice = args[1].lower()
    if choice in ["tai", "xiu"]:
        force_result = choice
        await message.reply(f"✅ Đã thiết lập ép kết quả phiên tiếp theo ra: <b>{choice.upper()}</b>")
    else:
        await message.reply("❌ Lựa chọn không hợp lệ! Chỉ dùng <code>tai</code> hoặc <code>xiu</code>.")

@dp.message(Command("checkplayer"))
async def cmd_admin_checkplayer(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠️ Cú pháp: <code>/checkplayer (id)</code>")
        return
    try:
        target_id = int(args[1].replace("(", "").replace(")", ""))
        if target_id not in users_db:
            await message.reply("❌ Không tìm thấy người chơi này trong hệ thống!")
            return
        target_user = users_db[target_id]
        info_text = (
            f"🔍 <b>THÔNG TIN NGƯỜI CHƠI</b>\n\n"
            f"🆔 <b>ID:</b> <code>{target_id}</code>\n"
            f"👤 <b>Tên:</b> {target_user['name']}\n"
            f"💰 <b>Số dư:</b> <b>{target_user['balance']:,.0f} VND</b>\n"
            f"💳 <b>Tổng nạp:</b> {target_user['total_nap']:,.0f} VND\n"
            f"🔥 <b>Tổng cược:</b> {target_user['total_cuoc']:,.0f} VND\n"
            f"👥 <b>Số người đã mời:</b> {target_user.get('invite_count', 0)}"
        )
        await message.reply(info_text)
    except ValueError:
        await message.reply("❌ ID không hợp lệ!")

@dp.message(Command("taocode", "tao_code"))
async def cmd_admin_taocode_new(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("(", " ").replace(")", " ")
    args = text.split()
    if len(args) < 4:
        await message.reply("⚠️ Cú pháp: <code>/taocode (mã code) (số tiền) (số lượt dùng)</code>")
        return
    code = args[1].upper()
    try:
        amount = float(args[2])
        uses = int(args[3])
        active_codes[code] = {"amount": amount, "uses": uses, "expire_at": None}
        await message.reply(f"🎁 Đã tạo Giftcode <b>{code}</b>: <b>{amount:,.0f} VND</b> ({uses} lượt dùng)")
    except ValueError:
        await message.reply("❌ Số tiền hoặc số lượt không hợp lệ!")

@dp.message(Command("tbao"))
async def cmd_admin_tbao(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text_content = message.text.split(maxsplit=1)
    if len(text_content) < 2:
        await message.reply("⚠️ Cú pháp: <code>/tbao (nội dung)</code>")
        return
    
    notice_text = text_content[1].strip()
    if notice_text.startswith("(") and notice_text.endswith(")"):
        notice_text = notice_text[1:-1]
        
    broadcast_msg = f"📢 <b>THÔNG BÁO TỪ HỆ THỐNG</b> 📢\n\n{notice_text}"
    
    count = 0
    for user_id in list(users_db.keys()):
        try:
            await bot.send_message(user_id, broadcast_msg)
            count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
            
    if GROUP_CHAT_ID:
        try:
            await bot.send_message(GROUP_CHAT_ID, broadcast_msg)
        except Exception:
            pass
            
    await message.reply(f"✅ Đã gửi thông báo thành công tới {count} người dùng!")

@dp.message(Command("kmnap"))
async def cmd_admin_kmnap(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    text = message.text.replace("(", "").replace(")", "").replace("%", "").replace("x", "")
    args = text.split()
    if len(args) < 4:
        await message.reply("⚠️ Cú pháp: <code>/kmnap (x3%) (00:00 14/09/2026)</code>")
        return
    try:
        percent = float(args[1])
        time_str = f"{args[2]} {args[3]}"
        expire_at = datetime.strptime(time_str, "%H:%M %d/%m/%Y")
        
        promo_config["percent"] = percent
        promo_config["expire_at"] = expire_at
        
        await message.reply(f"✅ Đã kích hoạt Khuyến Mãi Nạp <b>+{percent}%</b> đến <b>{expire_at.strftime('%H:%M %d/%m/%Y')}</b>")
    except Exception as e:
        await message.reply(f"❌ Định dạng thời gian hoặc phần trăm không hợp lệ! Lỗi: {e}")

@dp.message(Command("cong"))
async def cmd_admin_cong(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        await message.reply("⚠️ Cú pháp: <code>/cong [User_ID] [Số_tiền]</code>")
        return
    try:
        target_id = int(args[1])
        amount = float(args[2])
        target_user = get_user(target_id)
        target_user["balance"] += amount
        await message.reply(f"✅ Đã cộng <b>{amount:,.0f} VND</b> cho ID <code>{target_id}</code>. Số dư mới: {target_user['balance']:,.0f} VND")
    except ValueError:
        await message.reply("❌ ID hoặc số tiền không hợp lệ!")

@dp.message(Command("tru"))
async def cmd_admin_tru(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        await message.reply("⚠️ Cú pháp: <code>/tru [User_ID] [Số_tiền]</code>")
        return
    try:
        target_id = int(args[1])
        amount = float(args[2])
        target_user = get_user(target_id)
        target_user["balance"] = max(0.0, target_user["balance"] - amount)
        await message.reply(f"✅ Đã trừ <b>{amount:,.0f} VND</b> của ID <code>{target_id}</code>. Số dư mới: {target_user['balance']:,.0f} VND")
    except ValueError:
        await message.reply("❌ ID hoặc số tiền không hợp lệ!")

@dp.message(Command("set_hu"))
async def cmd_admin_set_hu(message: types.Message):
    global current_jackpot
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠️ Cú pháp: <code>/set_hu [Số_tiền]</code>")
        return
    try:
        current_jackpot = float(args[1])
        await message.reply(f"🏺 Đã cập nhật Hũ Jackpot thành: <b>{current_jackpot:,.0f} VND</b>")
    except ValueError:
        await message.reply("❌ Số tiền không hợp lệ!")

# --- HÀM HỖ TRỢ XỬ LÝ SỐ TIỀN CƯỢC (HỖ TRỢ CƯỢC ALL / ALL IN) ---
def parse_bet_amount(arg_text: str, user_balance: float, min_amount: float = 1000.0):
    arg_text = arg_text.lower().strip()
    if arg_text in ["all", "allin", "tattay"]:
        return user_balance
    try:
        amt = float(arg_text)
        if amt >= min_amount:
            return amt
    except ValueError:
        pass
    return None

# --- LỆNH XEM DANH SÁCH LỆNH CỦA NGƯỜI CHƠI ---
@dp.message(Command("lenh"))
async def cmd_user_lenh(message: types.Message):
    text = (
        f"📜 <b>DANH SÁCH LỆNH DÀNH CHO NGƯỜI CHƠI</b>\n"
        f"*(Hỗ trợ cược dồn, cược all / all in, không cần dấu `/`)*\n\n"
        f"🎲 <b>CƯỢC TÀI XỈU - CHẮN LẺ (TRONG NHÓM):</b>\n"
        f"<b>Cược công khai (Hỗ trợ Cược Dồn & All):</b>\n"
        f"• Lệnh cược Tài: <code>tai [số tiền]</code> hoặc <code>tai all</code>\n"
        f"• Lệnh cược Xỉu: <code>xiu [số tiền]</code> hoặc <code>xiu all</code>\n"
        f"• Lệnh cược Chẵn: <code>chan [số tiền]</code> / <code>c [số tiền]</code> / <code>c all</code>\n"
        f"• Lệnh cược Lẻ: <code>le [số tiền]</code> / <code>l [số tiền]</code> / <code>l all</code>\n"
        f"<b>Cược ẩn danh:</b>\n"
        f"• Lệnh cược Tài ẩn danh: <code>tt [số tiền]</code> / <code>tt all</code>\n"
        f"• Lệnh cược Xỉu ẩn danh: <code>xx [số tiền]</code> / <code>xx all</code>\n"
        f"• Lệnh cược Chẵn ẩn danh: <code>cc [số tiền]</code> / <code>cc all</code>\n"
        f"• Lệnh cược Lẻ ẩn danh: <code>ll [số tiền]</code> / <code>ll all</code>\n\n"
        f"💳 <b>TÀI KHOẢN & GIAO DỊCH:</b>\n"
        f"• <code>/start</code> - Khởi động bot & mở menu chính\n"
        f"• <code>/sodu</code> - Kiểm tra số dư tài khoản\n"
        f"• <code>/nap</code> - Tạo lệnh nạp tiền\n"
        f"• <code>/rut (số tiền) (STK) (Ngân hàng)</code> - Rút tiền về ngân hàng\n"
        f"• <code>/code (MãCode)</code> - Nhập Giftcode nhận thưởng\n"
        f"• <code>/lenh</code> - Xem danh sách tất cả các lệnh người chơi\n\n"
        f"🎮 <b>CÚ PHÁP CÁC GAME KHÁC (Hỗ trợ 'all'):</b>\n"
        f"• Bỏng ngô: <code>ngo [số tiền]</code> / <code>ngo all</code>\n"
        f"• Bóng rổ: <code>br [số tiền]</code> / <code>br all</code>\n"
        f"• Bóng đá: <code>bd [số tiền]</code> / <code>bd all</code>\n"
        f"• Bowling: <code>chan [số tiền]</code> / <code>le [số tiền]</code> (hoặc <code>all</code>)\n"
        f"• Phi tiêu: <code>vong1 [số tiền]</code> đến <code>vong5 [số tiền]</code> (hoặc <code>all</code>)\n"
        f"• Kéo búa bao: <code>bua</code> | <code>keo</code> | <code>bao [số tiền]</code> (hoặc <code>all</code>)\n"
        f"• Cứu thương: <code>cuu [số tiền]</code> / <code>cuu all</code>\n"
        f"• Đèn đỏ đèn xanh: <code>vuot [số tiền]</code> / <code>vuot all</code>\n"
        f"• Rót rượu: <code>rot [số tiền]</code> / <code>rot all</code>\n"
        f"• Bầu cua: <code>[cửa 1] [cửa 2] [số tiền/all]</code>\n"
        f"• Máy Bay Avitor: <code>bay [số tiền]</code> / <code>bay all</code>"
    )
    await message.answer(text)

# --- XỬ LÝ LỆNH NGƯỜI DÙNG & NÚT BẤM ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    global GROUP_CHAT_ID
    if message.chat.type in ["group", "supergroup"]:
        GROUP_CHAT_ID = message.chat.id
        
    args = message.text.split()
    referrer_id = None
    if len(args) > 1 and args[1].isdigit():
        referrer_id = int(args[1])
        
    get_user(message.from_user.id, message.from_user.full_name, referrer_id)
    text = (
        f"💎 <b>BTV88 CLUB - CỔNG GAME TÀI XỈU UY TÍN</b> 💎\n\n"
        f"Chào mừng <b>{message.from_user.full_name}</b> đến với hệ thống tự động!\n\n"
        f"📜 <b>HƯỚNG DẪN CƯỢC NHANH TRONG NHÓM (Không cần dấu `/`, hỗ trợ cược dồn & all):</b>\n"
        f"• Đặt Tài: <code>tai 10000</code> hoặc <code>tai all</code>\n"
        f"• Đặt Xỉu: <code>xiu 10000</code> hoặc <code>xiu all</code>\n"
        f"• Đặt Chẵn: <code>chan 10000</code> hoặc <code>c all</code>\n"
        f"• Đặt Lẻ: <code>le 10000</code> hoặc <code>l all</code>\n\n"
        f"💳 <b>LỆNH GIAO DỊCH:</b>\n"
        f"• Kiểm tra ví: <code>/sodu</code>\n"
        f"• Nạp tiền: <code>/nap</code>\n"
        f"• Rút tiền: <code>/rut 200000 [SốTK] [NgânHàng]</code>\n"
        f"• Nhập Code: <code>/code [MãCode]</code>"
    )
    await message.answer(text, reply_markup=main_menu_kb)

@dp.message(F.text == "🤝 Giới Thiệu")
async def btn_referral(message: types.Message):
    user_id = message.from_user.id
    user = get_user(user_id, message.from_user.full_name)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    text = (
        f"🤝 <b>CHƯƠNG TRÌNH GIỚI THIỆU NHẬN HOA HỒNG 0.5%</b>\n\n"
        f"🔗 <b>Link giới thiệu của bạn:</b>\n<code>{ref_link}</code>\n\n"
        f"👥 <b>Số người đã mời được:</b> <b>{user.get('invite_count', 0)}</b> người\n"
        f"💰 <b>Hoa hồng tích lũy:</b> <b>{user.get('ref_commission', 0.0):,.0f} VND</b>\n\n"
        f"📌 <i>Khi bạn bè đăng ký qua link và nạp tiền, bạn sẽ nhận ngay 0.5% tiền nạp vào tài khoản!</i>"
    )
    await message.answer(text)

@dp.message(F.text == "👤 Tài Khoản Của Tôi")
async def btn_my_account(message: types.Message):
    user = get_user(message.from_user.id, message.from_user.full_name)
    username_text = f"@{message.from_user.username}" if message.from_user.username else "Chưa đặt"
    text = (
        f"👤 <b>THÔNG TIN TÀI KHOẢN</b>\n\n"
        f"🆔 <b>ID:</b> <code>{message.from_user.id}</code>\n"
        f"📛 <b>Tên:</b> {user['name']}\n"
        f"📱 <b>Username:</b> {username_text}\n"
        f"💰 <b>Số dư hiện tại:</b> <b>{user['balance']:,.0f} VND</b>\n"
        f"💳 <b>Tổng nạp:</b> {user['total_nap']:,.0f} VND\n"
        f"🔥 <b>Tổng cược:</b> {user['total_cuoc']:,.0f} VND\n"
        f"👥 <b>Đã mời:</b> {user.get('invite_count', 0)} người"
    )
    await message.answer(text)

# --- XỬ LÝ NÚT DANH SÁCH GAME ---
@dp.message(F.text == "🎮 Danh Sách Game")
async def btn_game_list(message: types.Message):
    text = "🎮 <b>DANH SÁCH GAME CÓ SẴN BTV88 CLUB</b>\n\nBấm vào các nút bên dưới để xem hướng dẫn và cú pháp chơi từng game:"
    await message.answer(text, reply_markup=get_game_list_inline_kb())

# --- CALLBACK QUERY HANDLER CHO DANH SÁCH GAME ---
@dp.callback_query(F.data.startswith("game_"))
async def process_game_callback(callback: types.CallbackQuery, state: FSMContext):
    await callback.answer()
    game_code = callback.data
    
    if game_code == "game_close":
        try:
            await callback.message.delete()
        except Exception:
            pass
        return

    if game_code == "game_tx":
        text = (
            "🎲 <b>GAME TÀI XỈU 3D</b>\n\n"
            "📌 <b>Hướng dẫn chơi:</b> Nhắn trực tiếp trong nhóm chat (Hỗ trợ cược dồn & all).\n"
            "• Đặt Tài: <code>tai [số tiền]</code> hoặc <code>tai all</code>\n"
            "• Đặt Xỉu: <code>xiu [số tiền]</code> hoặc <code>xiu all</code>\n\n"
            "👉 <b>Link Room tung xúc xắc:</b> https://t.me/btv88club"
        )
    elif game_code == "game_cl":
        text = (
            "⚫️ <b>GAME CHẮN LẺ</b>\n\n"
            "📌 <b>Hướng dẫn chơi:</b> Nhắn trực tiếp trong nhóm chat (Hỗ trợ cược dồn & all).\n"
            "• Đặt Chẵn: <code>chan [số tiền]</code> / <code>c all</code>\n"
            "• Đặt Lẻ: <code>le [số tiền]</code> / <code>l all</code>\n\n"
            "👉 <b>Link Room tung chẵn lẻ:</b> https://t.me/btv88club"
        )
    elif game_code == "game_ngo":
        text = (
            "🍿 <b>GAME BỎNG NGÔ</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "• Ngô Đổ Tràn Ra Ngoài Là <b>THUA</b>\n"
            "• Ngô Không Tràn Ra Ngoài Là <b>THẮNG</b>\n"
            "• <b>Tỉ lệ trả thưởng:</b> Thắng x8,5 SỐ TIỀN CƯỢC\n\n"
            "📌 <b>Lệnh đặt cược:</b> <code>ngo [số tiền cược]</code> hoặc <code>ngo all</code> (Cược tối thiểu 20,000đ)"
        )
    elif game_code == "game_br":
        text = (
            "🏀 <b>GAME BÓNG RỔ</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "• Tung Bóng Vào Rổ Là <b>THẮNG</b>\n"
            "• Tung Bóng Ra Ngoài Là <b>THUA</b>\n"
            "• <b>Tỉ lệ trả thưởng:</b> x1,90 số tiền cược\n\n"
            "📌 <b>Lệnh đặt cược:</b> <code>br [số tiền cược]</code> hoặc <code>br all</code> (Cược tối thiểu 10,000đ)"
        )
    elif game_code == "game_bd":
        text = (
            "⚽️ <b>GAME BÓNG ĐÁ</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "• Sút Vào Gôn Là <b>THẮNG</b>\n"
            "• Sút Ra Ngoài Là <b>THUA</b>\n"
            "• <b>Tỉ lệ trả thưởng:</b> x1,5 số tiền cược\n\n"
            "📌 <b>Lệnh đặt cược:</b> <code>bd [số tiền cược]</code> atau <code>bd all</code> (Cược tối thiểu 10,000đ)"
        )
    elif game_code == "game_bw":
        text = (
            "🎳 <b>BOWLING CHẮN LẺ</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "• Ném bóng đổ 2,4,6 chai là <b>CHẲN</b>\n"
            "• Ném bóng đổ 1,3,5 chai là <b>LẺ</b>\n"
            "• Ném ra ngoài là <b>THUA</b>\n"
            "• <b>Tỉ lệ trả thưởng:</b> x1,90 số tiền cược\n\n"
            "📌 <b>Lệnh đặt cược:</b>\n"
            "• Cược Chẵn: <code>chan [số tiền]</code> hoặc <code>chan all</code>\n"
            "• Cược Lẻ: <code>le [số tiền]</code> atau <code>le all</code>\n"
            "(Cược tối thiểu 10,000đ)"
        )
    elif game_code == "game_pt":
        text = (
            "🎯 <b>GAME PHI TIÊU</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "Chọn vòng mà phi tiêu sẽ phi vào bia đỡ tính từ vòng 1 (tâm ở giữa) đến 5 (tâm ngoài cùng)\n"
            "• Phi Tiêu Trúng Vòng Mình Cược Là <b>THẮNG</b>\n"
            "• Phi Tiêu Trúng Vòng Khác Là <b>THUA</b>\n"
            "• Phi Tiêu ra ngoài là <b>THUA</b>\n"
            "• <b>Tỉ lệ trả thưởng:</b> x2 số tiền cược\n\n"
            "📌 <b>Lệnh đặt cược (Hỗ trợ all):</b>\n"
            "• Vòng 1: <code>vong1 [số tiền/all]</code>\n"
            "• Vòng 2: <code>vong2 [số tiền/all]</code>\n"
            "• Vòng 3: <code>vong3 [số tiền/all]</code>\n"
            "• Vòng 4: <code>vong4 [số tiền/all]</code>\n"
            "• Vòng 5: <code>vong5 [số tiền/all]</code>\n"
            "(Cược tối thiểu 10,000đ)"
        )
    elif game_code == "game_kbb":
        text = (
            "🖐️✌️👊 <b>GAME KÉO BÚA BAO</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "• Chọn ✌️(Kéo): Thắng 🖐️ - Thua 👊 - Hoà ✌️\n"
            "• Chọn 👊(Búa): Thắng ✌️ - Thua 🖐️ - Hoà 🖐️\n"
            "• Chọn 🖐️(Bao): Thắng 👊 - Thua ✌️ - Hoà 🖐️\n"
            "• <b>Tỉ lệ trả thưởng khi thắng:</b> x1,95 số tiền cược\n"
            "• <b>Hoà:</b> Hoàn lại 50% số tiền cược\n\n"
            "📌 <b>Lệnh đặt cược (Hỗ trợ all):</b>\n"
            "• Chọn Búa 👊: <code>bua [số tiền/all]</code>\n"
            "• Chọn Kéo ✌️: <code>keo [số tiền/all]</code>\n"
            "• Chọn Bao 🖐️: <code>bao [số tiền/all]</code>\n"
            "(Cược tối thiểu 10,000đ)"
        )
    elif game_code == "game_slot_pg":
        text = (
            "🎰 SLOT PG:\n"
            "👉 Gửi emoji Slot Telegram thật 🎰 để chơi.\n"
            "👉 Khi BOT trả lời mới được tính là đã đặt cược thành công.\n"
            "🌟 Thể lệ:\n"
            "Bot sẽ trừ tiền và tự động tung icon 🎰 có hoạt ảnh của telegram và đối chiếu kết quả với:\n"
            "🎁 3 Nho: x10 số tiền cược\n"
            "🎁 3 Chanh: x10 số tiền cược\n"
            "🎁 3 Bar: x15 số tiền cược\n"
            "🎁 777: x25 số tiền cược\n\n"
            "🚀 Phí: 1.000/1 lần cược\n\n"
            "👉 Vui lòng nhập số lượt quay bạn muốn cược:"
        )
        await state.set_state(SlotPGState.waiting_for_spins)
    elif game_code == "game_cuu_thuong":
        text = (
            "🚑 <b>GAME CỨU THƯƠNG</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "Xe cứu thương Đổ là Thắng (x3,5 tiền cược)\n"
            "Xe cứu thương Không Đổ là Thua\n\n"
            "Lệnh đặt cược: <code>cuu [số tiền]</code> atau <code>cuu all</code>"
        )
    elif game_code == "game_den_do_den_xanh":
        text = (
            "🚙 <b>GAME ĐÈN ĐỎ ĐÈN XANH</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "Xe Vượt đèn Đỏ là Thắng (X2,2 số tiền cược)\n"
            "Xe Dừng đèn Đỏ là Thua\n\n"
            "Lệnh đặt cược: <code>vuot [số tiền]</code> atau <code>vuot all</code>"
        )
    elif game_code == "game_rot_ruou":
        text = (
            "🍷 <b>GAME RÓT RƯỢU</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "Rót rượu đầy cốc là Thắng (x2,5 số tiền cược)\n"
            "Rót rượu không đầy cốc là Thua\n"
            "Rót rượu tràn ra khỏi cốc là Nổ Hũ (x99 số tiền cược)\n\n"
            "Lệnh đặt cược: <code>rot [số tiền]</code> hoặc <code>rot all</code>"
        )
    elif game_code == "game_bau_cua":
        text = (
            "🎲 <b>BẦU CUA</b>\n\n"
            "🍐 BẦU  - Nếu xúc xắc ra số 1\n"
            "🦐 TÔM  - Nếu xúc xắc ra số 2\n"
            "🦀 CUA  - Nếu xúc xắc ra số 3\n"
            "🐟 CÁ   - Nếu xúc xắc ra số 4\n"
            "🐓 GÀ   - Nếu xúc xắc ra số 5\n"
            "🦌 NAI  - Nếu xúc xắc ra số 6\n\n"
            "Tỷ lệ: ra 1 viên x1.95 | ra 2 viên x3 | ra 3 viên x4\n"
            "Đặt tối đa 3 cửa trong 1 lệnh.\n\n"
            "👉 Tối thiểu là 2.000 và tối đa là 300.000\n\n"
            "👉 Cách chơi: [cửa 1] [cửa 2] [tiền cược / all]\n"
            "VD: <code>bau cua ca 5000</code> hoặc <code>cua all</code>"
        )
    elif game_code == "game_aviator":
        user_id = callback.from_user.id
        history_list = aviator_history.get(user_id, [])
        history_text = "\n".join(history_list[-5:]) if history_list else "Chưa có lịch sử cược"
        text = (
            "🛩️ <b>MÁY BAY AVITOR</b>\n\n"
            "Máy Bay ✈️ - Bay càng cao X càng lớn\n\n"
            "📊 <b>Thống kê các phiên bay gần đây:</b>\n"
            f"{history_text}\n\n"
            "📌 <b>Lệnh đặt cược:</b> <code>bay [số tiền]</code> hoặc <code>bay all</code>"
        )
    else:
        text = "Mục game đang cập nhật!"

    try:
        await callback.message.answer(text)
    except Exception as e:
        logging.error(f"Lỗi gửi tin nhắn callback: {e}")

# --- XỬ LÝ NHẬP SỐ LƯỢT QUAY SLOT PG ---
@dp.message(SlotPGState.waiting_for_spins)
async def process_slot_spins_input(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.reply("❌ Vui lòng nhập số lượt quay hợp lệ! Ví dụ: 5")
        return
    
    spins = int(message.text)
    if spins <= 0:
        await message.reply("❌ Số lượt quay phải lớn hơn 0!")
        return

    user = get_user(message.from_user.id, message.from_user.full_name)
    total_cost = spins * 1000.0

    if user["balance"] < total_cost:
        await message.reply(f"❌ Số dư không đủ! Cần {total_cost:,.0f} VND cho {spins} lượt quay. Số dư hiện tại: {user['balance']:,.0f} VND")
        await state.clear()
        return

    await state.clear()
    user["balance"] -= total_cost
    user["total_cuoc"] += total_cost

    await message.reply(f"🎰 Đã trừ <b>{total_cost:,.0f} VND</b> cho <b>{spins}</b> lượt quay PG Slot. Đang tiến hành quay...")

    slot_outcomes = {
        1: ("BAR BAR BAR", 15.0),
        22: ("Nho Nho Nho", 10.0),
        43: ("Chanh Chanh Chanh", 10.0),
        64: ("777", 25.0)
    }

    total_won = 0.0

    for idx in range(1, spins + 1):
        dice_msg = await bot.send_dice(chat_id=message.chat.id, emoji="🎰")
        await asyncio.sleep(2.5)
        val = dice_msg.dice.value

        if val in slot_outcomes:
            name, rate = slot_outcomes[val]
            win_amt = 1000.0 * rate
            total_won += win_amt
            user["balance"] += win_amt
            await message.reply(f"🎉 Lượt quay {idx}/{spins}: Trúng <b>{name}</b>! Nhận thưởng <b>+{win_amt:,.0f} VND</b> (x{rate:.0f})")
        else:
            await message.reply(f"❌ Lượt quay {idx}/{spins}: Thua! (Không ra 3 Nho, 3 Chanh, 3 Bar, 777)")

    await message.reply(
        f"🏁 <b>KẾT QUẢ TỔNG CỘNG SLOT PG:</b>\n"
        f"• Tổng lượt quay: {spins}\n"
        f"• Tổng tiền cược: {total_cost:,.0f} VND\n"
        f"• Tổng tiền thắng: <b>+{total_won:,.0f} VND</b>\n"
        f"💰 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
    )

@dp.message(Command("sodu"))
@dp.message(F.text == "💰 Số Dư")
async def cmd_sodu(message: types.Message):
    user = get_user(message.from_user.id, message.from_user.full_name)
    await message.reply(f"💰 Số dư hiện tại của bạn: <b>{user['balance']:,.0f} VND</b>")

# --- NẠP TIỀN XÁC NHẬN BỞI ADMIN ---
@dp.message(Command("nap"))
@dp.message(F.text == "💳 Nạp Tiền")
async def cmd_nap(message: types.Message, state: FSMContext):
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        amount = int(args[1])
        await process_nap_amount(message, amount, state)
    else:
        await state.set_state(NapMoneyState.waiting_for_amount)
        await message.reply("💵 Vui lòng nhập số tiền bạn muốn nạp (tối thiểu <b>10,000đ</b>):")

@dp.message(NapMoneyState.waiting_for_amount)
async def process_nap_input(message: types.Message, state: FSMContext):
    if not message.text or not message.text.isdigit():
        await message.reply("❌ Vui lòng chỉ nhập số nguyên hợp lệ! Ví dụ: 50000")
        return
    
    amount = int(message.text)
    await process_nap_amount(message, amount, state)

async def process_nap_amount(message: types.Message, amount: int, state: FSMContext):
    if amount < 10000:
        await message.reply("❌ Số tiền nạp tối thiểu là <b>10,000đ</b>! Vui lòng nhập lại số tiền hợp lệ:")
        return

    await state.clear()
    user_id = message.from_user.id
    name = message.from_user.full_name
    username = f"@{message.from_user.username}" if message.from_user.username else name
    user = get_user(user_id, name)
    content_nap = f"NAP{user_id}{random.randint(1000,9999)}"
    
    bonus_promo = 0.0
    if promo_config["expire_at"] and datetime.now() <= promo_config["expire_at"]:
        bonus_promo = amount * (promo_config["percent"] / 100.0)
        
    total_add = amount + bonus_promo

    qr_caption = (
        f"💳 <b>HƯỚNG DẪN NẠP TIỀN</b> 💳\n\n"
        f"📌 <b>BƯỚC 1:</b> Quét mã QR bên dưới hoặc chuyển khoản thủ công theo thông tin:\n"
        f"• Ngân hàng: <b>ACB BANK</b>\n"
        f"• Số tài khoản: <code>27673211</code>\n"
        f"• Chủ tài khoản: <b>KHONG QUOC BAO</b>\n"
        f"• Số tiền: <b>{amount:,.0f} VND</b>\n"
        f"• Nội dung CK bắt buộc: <code>{content_nap}</code>\n\n"
        f"📌 <b>BƯỚC 2:</b> Sau khi chuyển khoản xong, vui lòng chờ Admin xác nhận. Tiền sẽ được cộng tự động ngay khi được duyệt.\n"
        f"⚠️ <i>Lưu ý: Chuyển đúng nội dung để lệnh được duyệt nhanh nhất!</i>"
    )
    if bonus_promo > 0:
        qr_caption += f"\n\n🎁 <b>Khuyến mãi áp dụng:</b> +{promo_config['percent']}% ({bonus_promo:,.0f} VND) thành {total_add:,.0f} VND!"

    qr_url = f"https://img.vietqr.io/image/ACB-27673211-compact.png?amount={amount}&addInfo={content_nap}&accountName=KHONG%20QUOC%20BAO"

    try:
        await message.answer_photo(photo=qr_url, caption=qr_caption)
    except Exception:
        await message.answer(qr_caption)

    # Gửi yêu cầu duyệt đến Admin
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Đồng ý cộng tiền", callback_data=f"nap_approve_{user_id}_{amount}_{total_add}_{content_nap}"),
            InlineKeyboardButton(text="❌ Từ chối", callback_data=f"nap_deny_{user_id}_{amount}")
        ]
    ])

    try:
        admin_notice = (
            f"📥 <b>YÊU CẦU NẠP TIỀN MỚI CẦN DUYỆT</b>\n\n"
            f"👤 Khách hàng: <b>{name}</b> ({username})\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"💵 Số tiền nạp: <b>{amount:,.0f} VND</b>\n"
            f"🎁 Thực nhận (+KM): <b>{total_add:,.0f} VND</b>\n"
            f"📝 Nội dung CK: <code>{content_nap}</code>"
        )
        await bot.send_message(ADMIN_ID, admin_notice, reply_markup=admin_kb)
    except Exception as e:
        logging.error(f"Không thể gửi thông báo duyệt nạp cho Admin: {e}")

@dp.callback_query(F.data.startswith("nap_"))
async def process_nap_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⚠️ Bạn không có quyền thực hiện hành động này!", show_alert=True)
        return

    data = callback.data.split("_")
    action = data[1]
    
    if action == "approve":
        target_id = int(data[2])
        amount = float(data[3])
        total_add = float(data[4])
        content_nap = data[5]
        
        target_user = get_user(target_id)
        target_user["history_nap"].append(f"Nạp {amount:,.0f} VND (+KM: {total_add - amount:,.0f} VND) [{content_nap}]")
        target_user["total_nap"] += amount
        target_user["balance"] += total_add

        # Hoa hồng giới thiệu
        ref_id = target_user.get("referrer_id")
        if ref_id and ref_id in users_db:
            ref_bonus = amount * 0.005
            users_db[ref_id]["balance"] += ref_bonus
            users_db[ref_id]["ref_commission"] = users_db[ref_id].get("ref_commission", 0.0) + ref_bonus
            try:
                await bot.send_message(
                    ref_id, 
                    f"🎉 Bạn nhận được <b>{ref_bonus:,.0f} VND</b> hoa hồng (0.5%) từ giao dịch nạp tiền của <b>{target_user['name']}</b>!"
                )
            except Exception:
                pass

        try:
            await bot.send_message(
                target_id,
                f"✅ <b>LỆNH NẠP TIỀN ĐÃ ĐƯỢC DUYỆT!</b>\n\n"
                f"💰 Số tiền cộng: <b>+{total_add:,.0f} VND</b>\n"
                f"💳 Số dư hiện tại: <b>{target_user['balance']:,.0f} VND</b>\n"
                f"🚀 Chúc bạn chơi game may mắn và đại thắng!"
            )
        except Exception:
            pass

        if GROUP_CHAT_ID:
            try:
                await bot.send_message(
                    GROUP_CHAT_ID,
                    f"✅ <b>THÔNG BÁO NẠP TIỀN THÀNH CÔNG</b>\n\n"
                    f"🆔 <b>ID người chơi:</b> <code>{target_id}</code>\n"
                    f"💰 <b>Số tiền nạp:</b> <b>{total_add:,.0f} VND</b>"
                )
            except Exception:
                pass

        await callback.message.edit_text(
            f"{callback.message.html_text}\n\n🟢 <b>ĐÃ ĐỒNG Ý DUYỆT CỘNG {total_add:,.0f} VND</b>"
        )
        await callback.answer("✅ Đã cộng tiền thành công!")

    elif action == "deny":
        target_id = int(data[2])
        amount = float(data[3])
        
        try:
            await bot.send_message(
                target_id,
                f"❌ <b>LỆNH NẠP TIỀN BỊ TỪ CHỐI!</b>\n\n"
                f"Yêu cầu nạp <b>{amount:,.0f} VND</b> của bạn đã bị Admin từ chối.\n"
                f"Vui lòng liên hệ CSKH nếu có thắc mắc!"
            )
        except Exception:
            pass

        await callback.message.edit_text(
            f"{callback.message.html_text}\n\n🔴 <b>ĐÃ TỪ CHỐI YÊU CẦU NẠP TIỀN</b>"
        )
        await callback.answer("❌ Đã từ chối lệnh nạp!")

@dp.message(Command("rut"))
@dp.message(F.text == "💸 Rút Tiền")
async def cmd_rut(message: types.Message):
    args = message.text.split(maxsplit=3)
    user_id = message.from_user.id
    name = message.from_user.full_name
    username = f"@{message.from_user.username}" if message.from_user.username else name
    user = get_user(user_id, name)
    
    if len(args) < 4:
        await message.reply("🏛️ Cú pháp rút tiền: <code>/rut [Số tiền] [Số TK] [Ngân hàng]</code>")
        return
    try:
        amount = float(args[1])
        stk, bank = args[2], args[3]
    except ValueError:
        await message.reply("❌ Số tiền không hợp lệ.")
        return
        
    if user["balance"] < amount:
        await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND")
        return
        
    user["balance"] -= amount
    user["history_rut"].append(f"Rút {amount:,.0f} VND -> STK: {stk} ({bank})")
    await message.reply(f"✅ Đã tạo lệnh rút <b>{amount:,.0f} VND</b> về TK <code>{stk} ({bank})</code> thành công!")

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Duyệt Rút", callback_data=f"rut_approve_{user_id}_{amount}"),
            InlineKeyboardButton(text="❌ Từ chối", callback_data=f"rut_deny_{user_id}_{amount}")
        ]
    ])

    try:
        admin_notice = (
            f"📤 <b>YÊU CẦU RÚT TIỀN MỚI</b>\n\n"
            f"👤 Khách hàng: <b>{name}</b> ({username})\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"💸 Số tiền rút: <b>{amount:,.0f} VND</b>\n"
            f"🏦 STK: <code>{stk}</code>\n"
            f"🏛️ Ngân hàng: <b>{bank}</b>\n"
            f"💰 Số dư còn lại: {user['balance']:,.0f} VND"
        )
        await bot.send_message(ADMIN_ID, admin_notice, reply_markup=admin_kb)
    except Exception as e:
        logging.error(f"Không thể gửi thông báo cho Admin: {e}")

@dp.callback_query(F.data.startswith("rut_"))
async def process_rut_callback(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⚠️ Bạn không có quyền thực hiện hành động này!", show_alert=True)
        return

    data = callback.data.split("_")
    action = data[1]
    target_id = int(data[2])
    amount = float(data[3])

    if action == "approve":
        try:
            await bot.send_message(
                target_id,
                f"✅ <b>LỆNH RÚT TIỀN ĐÃ ĐƯỢC DUYỆT!</b>\n\n"
                f"💸 Số tiền rút: <b>{amount:,.0f} VND</b>\n"
                f"🚀 Tiền đã được chuyển vào tài khoản của bạn!"
            )
        except Exception:
            pass

        if GROUP_CHAT_ID:
            try:
                await bot.send_message(
                    GROUP_CHAT_ID,
                    f"✅ <b>THÔNG BÁO RÚT TIỀN THÀNH CÔNG</b>\n\n"
                    f"🆔 <b>ID người chơi:</b> <code>{target_id}</code>\n"
                    f"💸 <b>Số tiền rút:</b> <b>{amount:,.0f} VND</b>"
                )
            except Exception:
                pass

        await callback.message.edit_text(
            f"{callback.message.html_text}\n\n🟢 <b>ĐÃ DUYỆT RÚT TIỀN {amount:,.0f} VND</b>"
        )
        await callback.answer("✅ Đã duyệt lệnh rút!")

    elif action == "deny":
        target_user = get_user(target_id)
        target_user["balance"] += amount
        try:
            await bot.send_message(
                target_id,
                f"❌ <b>LỆNH RÚT TIỀN BỊ TỪ CHỐI!</b>\n\n"
                f"Lệnh rút <b>{amount:,.0f} VND</b> của bạn đã bị từ chối và tiền đã được hoàn về ví."
            )
        except Exception:
            pass

        await callback.message.edit_text(
            f"{callback.message.html_text}\n\n🔴 <b>ĐÃ TỪ CHỐI RÚT TIỀN & HOÀN TIỀN</b>"
        )
        await callback.answer("❌ Đã từ chối lệnh rút!")

@dp.message(F.text == "🏆 Top Nạp")
async def btn_top_nap(message: types.Message):
    sorted_users = sorted(users_db.items(), key=lambda x: x[1]["total_nap"], reverse=True)[:5]
    text = "🏆 <b>BẢNG XẾP HẠNG TOP NẠP</b> 🏆\n\n"
    for idx, (uid, udata) in enumerate(sorted_users, 1):
        text += f"{idx}. <b>{udata['name']}</b>: {udata['total_nap']:,.0f} VND\n"
    await message.answer(text)

@dp.message(F.text == "🔥 Top Cược")
async def btn_top_cuoc(message: types.Message):
    sorted_users = sorted(users_db.items(), key=lambda x: x[1]["total_cuoc"], reverse=True)[:5]
    text = "🔥 <b>BẢNG XẾP HẠNG TOP CƯỢC</b> 🔥\n\n"
    for idx, (uid, udata) in enumerate(sorted_users, 1):
        text += f"{idx}. <b>{udata['name']}</b>: {udata['total_cuoc']:,.0f} VND\n"
    await message.answer(text)

@dp.message(F.text == "📜 Lịch Sử Nạp")
async def btn_history_nap(message: types.Message):
    user = get_user(message.from_user.id, message.from_user.full_name)
    if not user["history_nap"]:
        await message.answer("📜 Bạn chưa có lịch sử nạp tiền.")
        return
    text = "💳 <b>LỊCH SỬ NẠP TIỀN GẦN ĐÂY:</b>\n\n" + "\n".join([f"• {item}" for item in user["history_nap"][-5:]])
    await message.answer(text)

@dp.message(F.text == "📜 Lịch Sử Rút")
async def btn_history_rut(message: types.Message):
    user = get_user(message.from_user.id, message.from_user.full_name)
    if not user["history_rut"]:
        await message.answer("📜 Bạn chưa có lịch sử rút tiền.")
        return
    text = "💸 <b>LỊCH SỬ RÚT TIỀN GẦN ĐÂY:</b>\n\n" + "\n".join([f"• {item}" for item in user["history_rut"][-5:]])
    await message.answer(text)

@dp.message(F.text == "🎧 CSKH")
async def btn_cskh(message: types.Message):
    text = (
        "🎧 <b>MỌI VẤN ĐỀ VUI LÒNG LIÊN HỆ:</b>\n\n"
        "<b>CSKH:</b> @cskhbtv88club"
    )
    await message.answer(text)

@dp.message(Command("code"))
@dp.message(F.text == "🎁 Nhập Code")
async def cmd_code(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠️ Cú pháp: <code>/code [MãCode]</code>")
        return
    code = args[1].upper()
    user = get_user(message.from_user.id, message.from_user.full_name)
    
    if code not in active_codes:
        await message.reply("❌ Mã Giftcode không tồn tại hoặc đã hết hạn!")
        return
        
    gift = active_codes[code]
    
    if gift.get("expire_at") and datetime.now() > gift["expire_at"]:
        del active_codes[code]
        await message.reply("❌ Mã Giftcode này đã quá thời gian sử dụng!")
        return

    if gift["uses"] <= 0:
        del active_codes[code]
        await message.reply("❌ Mã Giftcode này đã được sử dụng hết lượt!")
        return

    user["balance"] += gift["amount"]
    gift["uses"] -= 1
    
    if gift["uses"] <= 0:
        del active_codes[code]

    await message.reply(f"🎁 Bạn nhận được <b>{gift['amount']:,.0f} VND</b> từ Giftcode <code>{code}</code>!")

# --- XỬ LÝ GAME MÁY BAY AVIATOR ---
@dp.message(Command("bay"))
async def cmd_game_aviator_bay(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    user = get_user(user_id, name)
    parts = message.text.split()
    if len(parts) < 2:
        await message.reply("⚠️ Cú pháp: <code>bay (số tiền cược)</code> hoặc <code>bay all</code>")
        return
    
    amount = parse_bet_amount(parts[1], user["balance"], min_amount=1000.0)
    if amount is None or amount < 1000:
        await message.reply("⚠️ Số tiền cược tối thiểu là 1,000đ hoặc không hợp lệ!")
        return
    if user["balance"] < amount:
        await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND")
        return

    if user_id in aviator_active_games and aviator_active_games[user_id].get("active", False):
        await message.reply("⚠️ Bạn đang có một phiên bay đang diễn ra, vui lòng chờ phiên kết thúc!")
        return

    user["balance"] -= amount
    user["total_cuoc"] += amount

    turn = aviator_user_turn.get(user_id, 1)
    if turn == 1:
        target_x = round(random.uniform(0.0, 1.85), 2)
    elif turn == 2:
        target_x = round(random.uniform(0.0, 0.3), 2)
    elif turn == 3:
        target_x = round(random.uniform(0.0, 0.8), 2)
    elif turn == 4:
        target_x = round(random.uniform(0.0, 1.2), 2)
    elif turn == 5:
        target_x = round(random.uniform(0.0, 0.6), 2)
    elif turn == 6:
        target_x = round(random.uniform(0.0, 2.5), 2)
    elif turn == 7:
        target_x = round(random.uniform(0.0, 0.6), 2)
    elif turn == 8:
        target_x = round(random.uniform(0.0, 2.7), 2)
    elif turn == 9:
        target_x = round(random.uniform(0.0, 0.6), 2)
    elif turn == 10:
        target_x = round(random.uniform(0.0, 0.6), 2)
    elif turn in [11, 12]:
        target_x = 0.0
    elif turn == 13:
        target_x = round(random.uniform(0.0, 15.0), 2)
    else:
        target_x = round(random.uniform(0.0, 1.85), 2)

    aviator_user_turn[user_id] = 1 if turn >= 13 else turn + 1

    await bot.send_message(message.chat.id, "🛩️")
    await message.reply("🚀 Máy bay bắt đầu cất cánh! Chúc bạn may mắn!")

    stop_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛑 DỪNG BAY", callback_data=f"aviator_stop_{user_id}")]
    ])

    status_msg = await bot.send_message(
        message.chat.id,
        f"🛩️ <b>MÁY BAY ĐANG BAY...</b>\n\n"
        f"💰 Số tiền cược: <b>{amount:,.0f} VND</b>\n"
        f"📈 Hệ số x hiện tại: <b>x0.00</b>",
        reply_markup=stop_kb
    )

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💥 NỔ MÁY BAY", callback_data=f"aviator_explode_{user_id}")]
    ])
    try:
        admin_msg = await bot.send_message(
            ADMIN_ID,
            f"🛩️ <b>THÔNG BÁO KHÁCH BAY (AVIATOR)</b>\n\n"
            f"👤 Khách hàng: <b>{name}</b> (<code>{user_id}</code>)\n"
            f"💰 Số tiền cược: <b>{amount:,.0f} VND</b>\n"
            f"🎯 Hệ số tối đa phiên: <b>x{target_x:.2f}</b>\n"
            f"📈 Hệ số đang bay: <b>x0.00</b>",
            reply_markup=admin_kb
        )
        admin_msg_id = admin_msg.message_id
    except Exception:
        admin_msg_id = None

    aviator_active_games[user_id] = {
        "active": True,
        "amount": amount,
        "target_x": target_x,
        "current_x": 0.0,
        "status_msg_id": status_msg.message_id,
        "admin_msg_id": admin_msg_id,
        "chat_id": message.chat.id,
        "stopped": False,
        "exploded": False
    }

    asyncio.create_task(run_aviator_flight(user_id))

async def run_aviator_flight(user_id: int):
    game = aviator_active_games.get(user_id)
    if not game:
        return

    amount = game["amount"]
    target_x = game["target_x"]
    chat_id = game["chat_id"]
    status_msg_id = game["status_msg_id"]
    admin_msg_id = game["admin_msg_id"]

    curr_x = 0.0
    step = 0.1

    while curr_x < target_x and game["active"] and not game["stopped"] and not game["exploded"]:
        await asyncio.sleep(1.0)
        curr_x = round(curr_x + step, 2)
        if curr_x > target_x:
            curr_x = target_x
        game["current_x"] = curr_x

        stop_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🛑 DỪNG BAY", callback_data=f"aviator_stop_{user_id}")]
        ])
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_msg_id,
                text=f"🛩️ <b>MÁY BAY ĐANG BAY...</b>\n\n"
                     f"💰 Số tiền cược: <b>{amount:,.0f} VND</b>\n"
                     f"📈 Hệ số x hiện tại: <b>x{curr_x:.2f}</b>",
                reply_markup=stop_kb
            )
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after)
        except Exception:
            pass

        if admin_msg_id:
            admin_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💥 NỔ MÁY BAY", callback_data=f"aviator_explode_{user_id}")]
            ])
            try:
                await bot.edit_message_text(
                    chat_id=ADMIN_ID,
                    message_id=admin_msg_id,
                    text=f"🛩️ <b>THÔNG BÁO KHÁCH BAY (AVIATOR)</b>\n\n"
                         f"👤 ID: <code>{user_id}</code>\n"
                         f"💰 Số tiền cược: <b>{amount:,.0f} VND</b>\n"
                         f"🎯 Hệ số tối đa phiên: <b>x{target_x:.2f}</b>\n"
                         f"📈 Hệ số đang bay: <b>x{curr_x:.2f}</b>",
                    reply_markup=admin_kb
                )
            except Exception:
                pass

    if game["stopped"]:
        game["active"] = False
        return

    game["active"] = False
    
    if user_id not in aviator_history:
        aviator_history[user_id] = []
    aviator_history[user_id].append(f"Cược {amount:,.0f}đ - Kết quả: THUA (x{target_x:.2f})")

    try:
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=status_msg_id,
            text=f"💥 <b>MÁY BAY ĐÃ NỔ!</b>\n\n"
                 f"❌ Khách chưa dừng bay kịp thời!\n"
                 f"💰 Số tiền cược: <b>{amount:,.0f} VND</b>\n"
                 f"📈 Hệ số dừng: <b>x{target_x:.2f}</b>\n"
                 f"💸 Bạn đã <b>THUA</b> toàn bộ tiền cược!"
        )
    except Exception:
        pass

    if admin_msg_id:
        try:
            await bot.edit_message_text(
                chat_id=ADMIN_ID,
                message_id=admin_msg_id,
                text=f"💥 <b>MÁY BAY ĐÃ NỔ (KẾT THÚC)</b>\n\n"
                     f"👤 ID: <code>{user_id}</code>\n"
                     f"💰 Cược: <b>{amount:,.0f} VND</b> | Hệ số nổ: <b>x{target_x:.2f}</b>\n"
                     f"🔴 Khách đã THUA phiên này!"
            )
        except Exception:
            pass

@dp.callback_query(F.data.startswith("aviator_stop_"))
async def process_aviator_stop(callback: types.CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    if callback.from_user.id != user_id:
        await callback.answer("⚠️ Đây không phải phiên bay của bạn!", show_alert=True)
        return

    game = aviator_active_games.get(user_id)
    if not game or not game["active"] or game["stopped"]:
        await callback.answer("⚠️ Phiên bay đã kết thúc!", show_alert=True)
        return

    game["stopped"] = True
    game["active"] = False

    stopped_x = game["current_x"]
    amount = game["amount"]
    win_amount = amount * stopped_x

    user = get_user(user_id)
    user["balance"] += win_amount

    if user_id not in aviator_history:
        aviator_history[user_id] = []
    aviator_history[user_id].append(f"Cược {amount:,.0f}đ - THẮNG +{win_amount:,.0f}đ (x{stopped_x:.2f})")

    await callback.answer(f"🎉 Bạn đã dừng bay ở x{stopped_x:.2f}! Nhận {win_amount:,.0f} VND", show_alert=True)

    try:
        await bot.edit_message_text(
            chat_id=game["chat_id"],
            message_id=game["status_msg_id"],
            text=f"🎉 <b>DỪNG BAY THÀNH CÔNG!</b>\n\n"
                 f"💰 Tiền cược: <b>{amount:,.0f} VND</b>\n"
                 f"📈 Hệ số dừng bay: <b>x{stopped_x:.2f}</b>\n"
                 f"🏆 Tổng tiền thắng: <b>+{win_amount:,.0f} VND</b>\n"
                 f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
        )
    except Exception:
        pass

    if game.get("admin_msg_id"):
        try:
            await bot.edit_message_text(
                chat_id=ADMIN_ID,
                message_id=game["admin_msg_id"],
                text=f"🟢 <b>KHÁCH ĐÃ DỪNG BAY THÀNH CÔNG</b>\n\n"
                     f"👤 ID: <code>{user_id}</code>\n"
                     f"💰 Cược: <b>{amount:,.0f} VND</b> | Dừng ở: <b>x{stopped_x:.2f}</b>\n"
                     f"🏆 Tiền thắng: <b>+{win_amount:,.0f} VND</b>"
            )
        except Exception:
            pass

@dp.callback_query(F.data.startswith("aviator_explode_"))
async def process_aviator_explode(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("⚠️ Bạn không có quyền thực hiện!", show_alert=True)
        return

    user_id = int(callback.data.split("_")[2])
    game = aviator_active_games.get(user_id)

    if not game or not game["active"]:
        await callback.answer("⚠️ Phiên bay này đã kết thúc hoặc không tồn tại!", show_alert=True)
        return

    game["exploded"] = True
    game["target_x"] = game["current_x"]
    await callback.answer("💥 Đã cho nổ máy bay lập tức!", show_alert=True)

# --- VÒNG LẶP TỰ ĐỘNG TUNG XÚC XẮC TÀI XỈU & CHẮN LẺ (GỬI MỚI MỖI 5S, ICON LỊCH SỬ & CỘNG 1% TIỀN THUA VÀO HŨ) ---
async def auto_tai_xiu_loop():
    global current_session, current_jackpot, force_result, recent_tai_xiu, recent_chan_le, bets_current
    while True:
        if not GROUP_CHAT_ID:
            await asyncio.sleep(5)
            continue

        try:
            total_seconds = 45
            elapsed = 0
            current_stat_msg_id = None
            
            while elapsed < total_seconds:
                sum_tai = sum(b["amount"] for b in bets_current.values() if b["type"] == "tai")
                sum_xiu = sum(b["amount"] for b in bets_current.values() if b["type"] == "xiu")
                sum_chan = sum(b["amount"] for b in bets_current.values() if b["type"] == "chan")
                sum_le = sum(b["amount"] for b in bets_current.values() if b["type"] == "le")
                
                remaining = max(0, total_seconds - elapsed)
                
                stat_text = (
                    f"💎 <b>BTV88 CLUB - PHIÊN #{current_session}</b> 💎\n"
                    f"🏺 <b>Hũ Jackpot:</b> <b>{current_jackpot:,.0f} VND</b>\n\n"
                    f"⏳ <b>Thời gian đặt cược còn lại:</b> <code>{remaining}s</code> (Hỗ trợ cược dồn & all)\n\n"
                    f"📊 <b>Thống kê cược hiện tại:</b>\n"
                    f"• Cửa TÀI: <b>{sum_tai:,.0f} VND</b> | Cửa XỈU: <b>{sum_xiu:,.0f} VND</b>\n"
                    f"• Cửa CHẴN: <b>{sum_chan:,.0f} VND</b> | Cửa LẺ: <b>{sum_le:,.0f} VND</b>\n\n"
                    f"💡 <b>Lệnh cược Tài/Xỉu:</b> <code>tai [tiền/all]</code> | <code>xiu [tiền/all]</code> (Ẩn danh: <code>tt</code> / <code>xx</code>)\n"
                    f"💡 <b>Lệnh cược Chẵn/Lẻ:</b> <code>chan [tiền/all]</code> | <code>le [tiền/all]</code> (Ẩn danh: <code>cc</code> / <code>ll</code>)"
                )
                
                if current_stat_msg_id:
                    try:
                        await bot.delete_message(chat_id=GROUP_CHAT_ID, message_id=current_stat_msg_id)
                    except Exception:
                        pass
                
                new_msg = await bot.send_message(GROUP_CHAT_ID, stat_text)
                current_stat_msg_id = new_msg.message_id
                
                await asyncio.sleep(5)
                elapsed += 5

            if current_stat_msg_id:
                try:
                    await bot.delete_message(chat_id=GROUP_CHAT_ID, message_id=current_stat_msg_id)
                except Exception:
                    pass

            await lock_chat(GROUP_CHAT_ID)
            await bot.send_message(GROUP_CHAT_ID, f"🔒 <b>PHIÊN #{current_session} ĐÃ ĐÓNG CƯỢC!</b>\n⏳ Đang tiến hành tung xúc xắc...")
            
            await asyncio.sleep(2)
            
            d1_msg = await bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
            await asyncio.sleep(1)
            d2_msg = await bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
            await asyncio.sleep(1)
            d3_msg = await bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
            await asyncio.sleep(3)
            
            v1 = d1_msg.dice.value
            v2 = d2_msg.dice.value
            v3 = d3_msg.dice.value
            total_sum = v1 + v2 + v3
            
            is_jackpot = (total_sum == 3 or total_sum == 18)
            jackpot_winners_msg = ""

            if is_jackpot:
                jackpot_side = random.choice(['tai', 'xiu'])
                jackpot_bets = {uid: b for uid, b in bets_current.items() if b["type"] == jackpot_side}
                total_jp_bet = sum(b["amount"] for b in jackpot_bets.values())

                if total_jp_bet > 0:
                    win_details = []
                    for uid, b in jackpot_bets.items():
                        user_obj = get_user(uid)
                        reward = current_jackpot * (b["amount"] / total_jp_bet)
                        user_obj["balance"] += reward
                        win_details.append(f"• <b>{b['name']}</b> nhận <b>+{reward:,.0f}đ</b>")
                    jackpot_winners_msg = f"\n🏺💥 <b>NỔ HŨ CỬA {jackpot_side.upper()}! Trị giá {current_jackpot:,.0f}đ</b>\n" + "\n".join(win_details)
                current_jackpot = 600000.0

            if force_result:
                tx_result = force_result
                force_result = None
            else:
                tx_result = jackpot_side if is_jackpot else ('tai' if total_sum >= 11 else 'xiu')
                
            cl_result = 'chan' if total_sum % 2 == 0 else 'le'
            
            # Cập nhật lịch sử bằng 4 icon khác nhau: Tài (🟢), Xỉu (🔴) | Chẵn (🔵), Lẻ (🟡)
            recent_tai_xiu.append('🟢' if tx_result == 'tai' else '🔴')
            if len(recent_tai_xiu) > 12: recent_tai_xiu.pop(0)
            
            recent_chan_le.append('🔵' if cl_result == 'chan' else '🟡')
            if len(recent_chan_le) > 12: recent_chan_le.pop(0)

            # Xử lý trả thưởng, gửi thông báo riêng & tính tổng tiền thua để cộng 1% vào Hũ Jackpot
            total_lost_amount = 0.0

            for uid, bet in bets_current.items():
                user_obj = get_user(uid)
                b_type = bet["type"]
                b_amt = bet["amount"]
                
                is_win = (b_type == tx_result or b_type == cl_result)
                
                if is_win:
                    win_amt = b_amt * 1.95
                    user_obj["balance"] += win_amt
                    personal_notice = (
                        f"🎉 <b>THÔNG BÁO KẾT QUẢ PHIÊN #{current_session}</b>\n\n"
                        f"🎯 Cửa cược: <b>{b_type.upper()}</b> ({b_amt:,.0f} VND)\n"
                        f"🏆 Kết quả: <b>THẮNG</b>\n"
                        f"💰 Tiền thưởng nhận: <b>+{win_amt:,.0f} VND</b>\n"
                        f"💵 Số dư ví hiện tại: <b>{user_obj['balance']:,.0f} VND</b>"
                    )
                else:
                    total_lost_amount += b_amt  # Tích lũy tiền thua của khách
                    personal_notice = (
                        f"❌ <b>THÔNG BÁO KẾT QUẢ PHIÊN #{current_session}</b>\n\n"
                        f"🎯 Cửa cược: <b>{b_type.upper()}</b> ({b_amt:,.0f} VND)\n"
                        f"💸 Kết quả: <b>THUA</b>\n"
                        f"💵 Số dư ví hiện tại: <b>{user_obj['balance']:,.0f} VND</b>"
                    )
                
                try:
                    await bot.send_message(uid, personal_notice)
                except Exception:
                    pass

            # Tự động cộng 1% tổng tiền cược thua vào Hũ Jackpot
            if total_lost_amount > 0:
                current_jackpot += total_lost_amount * 0.01

            bets_current.clear()

            res_string = "TÀI (🟢)" if tx_result == 'tai' else "XỈU (🔴)"
            cl_string = "CHẴN (🔵)" if cl_result == 'chan' else "LẺ (🟡)"
            
            summary_text = (
                f"📊 <b>KẾT QUẢ PHIÊN #{current_session}</b> 📊\n\n"
                f"🎲 Xúc xắc: <b>{v1} - {v2} - {v3}</b> (Tổng: <b>{total_sum}</b>)\n"
                f"🏆 Kết quả: <b>{res_string} | {cl_string}</b>"
                f"{jackpot_winners_msg}\n\n"
                f"🏺 <b>Hũ hiện tại:</b> <b>{current_jackpot:,.0f} VND</b>\n"
                f"📜 Lịch sử Tài Xỉu: {' '.join(recent_tai_xiu[-10:])}\n"
                f"📜 Lịch sử Chẵn Lẻ: {' '.join(recent_chan_le[-10:])}\n"
            )
            await bot.send_message(GROUP_CHAT_ID, summary_text)

            current_session += 1
            
            await unlock_chat(GROUP_CHAT_ID)
            await asyncio.sleep(1)

        except Exception as e:
            logging.error(f"Lỗi trong vòng lặp auto tài xỉu: {e}")
            await asyncio.sleep(5)

# --- XỬ LÝ CÁC GAME TRONG NHÓM & MINI GAME CÁ NHÂN ---
@dp.message()
async def catch_all_messages(message: types.Message):
    global GROUP_CHAT_ID
    if not message.text:
        return
        
    text = message.text.strip()
    # BỎ QUA TẤT CẢ CÁC TIN NHẮN BẮT ĐẦU BẰNG DẤU GẠCH CHÉO (CHỨC NĂNG LỆNH CHÍNH /START, /SODU,...)
    if text.startswith("/"):
        return

    user_id = message.from_user.id
    name = message.from_user.full_name
    user = get_user(user_id, name)
    text_lower = text.lower()
    parts = text_lower.split()
    if not parts:
        return
    cmd = parts[0]

    if message.chat.type in ["group", "supergroup"]:
        if GROUP_CHAT_ID != message.chat.id:
            GROUP_CHAT_ID = message.chat.id
            
        valid_tx_cl_cmds = ["tai", "xiu", "c", "l", "chan", "le", "tt", "xx", "cc", "ll"]
        if cmd in valid_tx_cl_cmds:
            if len(parts) < 2:
                return
            
            amount = parse_bet_amount(parts[1], user["balance"], min_amount=1000.0)
            if amount is None or amount < 1000:
                return
            if user["balance"] < amount:
                await message.reply(f"❌ {name}, tài khoản không đủ tiền cược!")
                return
                    
            is_anonymous = cmd in ["tt", "xx", "cc", "ll"]
            
            if cmd in ["tai", "tt"]:
                bet_type = "tai"
            elif cmd in ["xiu", "xx"]:
                bet_type = "xiu"
            elif cmd in ["c", "chan", "cc"]:
                bet_type = "chan"
            else:
                bet_type = "le"

            user["balance"] -= amount
            user["total_cuoc"] += amount

            # --- TÍNH NĂNG CƯỢC DỒN ---
            if user_id in bets_current:
                if bets_current[user_id]["type"] == bet_type:
                    bets_current[user_id]["amount"] += amount
                    total_current_bet = bets_current[user_id]["amount"]
                    await message.reply(f"➕ <b>{name}</b> cược dồn thêm <b>{amount:,.0f} VND</b>. Tổng cược cửa <b>{bet_type.upper()}</b>: <b>{total_current_bet:,.0f} VND</b>")
                    return
                else:
                    old_type = bets_current[user_id]["type"]
                    refund_amt = bets_current[user_id]["amount"]
                    user["balance"] += refund_amt
                    user["total_cuoc"] -= refund_amt
                    
                    user["balance"] -= amount
                    user["total_cuoc"] += amount
                    bets_current[user_id] = {"type": bet_type, "amount": amount, "name": name, "anonymous": is_anonymous}
                    await message.reply(f"🔄 <b>{name}</b> đổi cửa từ {old_type.upper()} sang <b>{bet_type.upper()}</b> với số tiền <b>{amount:,.0f} VND</b> (Đã hoàn tiền cược cũ).")
                    return
            else:
                bets_current[user_id] = {"type": bet_type, "amount": amount, "name": name, "anonymous": is_anonymous}
                if amount > 100000:
                    try:
                        admin_alert = (
                            f"🚨 <b>THÔNG BÁO CƯỢC LỚN (>100K)</b> 🚨\n\n"
                            f"👤 <b>Người cược:</b> {name} (<code>{user_id}</code>)\n"
                            f"🎯 <b>Cửa cược:</b> <b>{bet_type.upper()}</b> "
                            f"{'(Ẩn danh)' if is_anonymous else ''}\n"
                            f"💰 <b>Số tiền cược:</b> <b>{amount:,.0f} VND</b>"
                        )
                        await bot.send_message(ADMIN_ID, admin_alert)
                    except Exception:
                        pass

                if is_anonymous:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await bot.send_message(
                        message.chat.id,
                        f"🥷 <b>{name}</b> cược ẩn danh <b>{amount:,.0f} VND</b> vào <b>{bet_type.upper()}</b>"
                    )
                else:
                    await message.reply(f"✅ <b>{name}</b> cược <b>{amount:,.0f} VND</b> vào <b>{bet_type.upper()}</b>!")
            return

    # GAME BỎNG NGÔ
    if cmd == "ngo":
        if len(parts) >= 2:
            amount = parse_bet_amount(parts[1], user["balance"], min_amount=20000.0)
            if amount is None or amount < 20000:
                await message.reply("⚠️ Cược tối thiểu cho game Bỏng Ngô là 20,000đ hoặc số dư không đủ!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return
            
            user["balance"] -= amount
            user["total_cuoc"] += amount
            
            loss_text = (
                f"🍿 <b>KẾT QUẢ BỎNG NGÔ:</b>\n"
                f"❌ Ngô Đổ Tràn Ra Ngoài! Bạn đã <b>THUA</b>!\n"
                f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                f"💰 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
            )
            await message.reply(loss_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>ngo [số tiền cược]</code> atau <code>ngo all</code>")
        return

    # GAME BÓNG RỔ
    if cmd == "br":
        if len(parts) >= 2:
            amount = parse_bet_amount(parts[1], user["balance"], min_amount=10000.0)
            if amount is None or amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Bóng Rổ là 10,000đ hoặc số dư không đủ!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            dice_msg = await bot.send_dice(chat_id=message.chat.id, emoji="🏀")
            await asyncio.sleep(3.5)
            val = dice_msg.dice.value
            if val in [4, 5]:
                win_amt = amount * 1.90
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ BÓNG RỔ:</b> THẮNG!\n"
                    f"🏀 Tung bóng vào rổ thành công!\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ BÓNG RỔ:</b> THUA!\n"
                    f"🏀 Tung bóng ra ngoài gôn!\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>br [số tiền cược]</code> atau <code>br all</code>")
        return

    # GAME BÓNG ĐÁ
    if cmd == "bd":
        if len(parts) >= 2:
            amount = parse_bet_amount(parts[1], user["balance"], min_amount=10000.0)
            if amount is None or amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Bóng Đá là 10,000đ hoặc số dư không đủ!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            dice_msg = await bot.send_dice(chat_id=message.chat.id, emoji="⚽")
            await asyncio.sleep(3.5)
            val = dice_msg.dice.value
            if val in [3, 4, 5]:
                win_amt = amount * 1.50
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ BÓNG ĐÁ:</b> THẮNG!\n"
                    f"⚽️ Sút bóng vào gôn thành công!\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ BÓNG ĐÁ:</b> THUA!\n"
                    f"⚽️ Sút bóng ra ngoài!\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>bd [số tiền cược]</code> atau <code>bd all</code>")
        return

    # GAME BOWLING
    if cmd in ["chan", "le"] and len(parts) >= 2:
        amount = parse_bet_amount(parts[1], user["balance"], min_amount=10000.0)
        if amount is None or amount < 10000:
            await message.reply("⚠️ Cược tối thiểu cho game Bowling là 10,000đ hoặc số dư không đủ!")
            return
        if user["balance"] < amount:
            await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND")
            return
        user["balance"] -= amount
        user["total_cuoc"] += amount
        dice = await bot.send_dice(chat_id=message.chat.id, emoji="🎳")
        await asyncio.sleep(3.5)
        val = dice.dice.value if dice.dice.value <= 6 else random.randint(1, 6)
        res_type = "chan" if val in [2, 4, 6] else "le"
        if res_type == cmd:
            win = amount * 1.90
            user["balance"] += win
            await message.reply(f"🎉 Bowling THẮNG <b>+{win:,.0f} VND</b>!")
        else:
            await message.reply(f"❌ Bowling THUA <b>-{amount:,.0f} VND</b>!")
        return

    # GAME PHI TIÊU
    if cmd.startswith("vong"):
        if len(parts) >= 2:
            try:
                target_vong = int(cmd.replace("vong", ""))
                amount = parse_bet_amount(parts[1], user["balance"], min_amount=10000.0)
            except ValueError:
                return

            if target_vong < 1 or target_vong > 5:
                await message.reply("⚠️ Vòng cược chỉ từ 1 đến 5!")
                return

            if amount is None or amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Phi Tiêu là 10,000đ hoặc số dư không đủ!")
                return

            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            dice_msg = await bot.send_dice(chat_id=message.chat.id, emoji="🎯")
            await asyncio.sleep(3.5)
            val = dice_msg.dice.value

            hit_vong = val if val <= 5 else 0

            if hit_vong == target_vong:
                win_amt = amount * 2.0
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ PHI TIÊU:</b> THẮNG!\n"
                    f"🎯 Phi tiêu trúng Vòng {hit_vong} (Đúng vòng bạn chọn)!\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                hit_desc = f"Vòng {hit_vong}" if hit_vong > 0 else "Ra ngoài"
                res_text = (
                    f"❌ <b>KẾT QUẢ PHI TIÊU:</b> THUA!\n"
                    f"🎯 Phi tiêu trúng: {hit_desc} (Bạn chọn Vòng {target_vong})\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>vong1 [số tiền/all]</code> ... <code>vong5 [số tiền/all]</code>")
        return

    # GAME KÉO BÚA BAO
    if cmd in ["bua", "keo", "bao"]:
        if len(parts) >= 2:
            user_choice = cmd
            amount = parse_bet_amount(parts[1], user["balance"], min_amount=10000.0)

            if amount is None or amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Kéo Búa Bao là 10,000đ hoặc số dư không đủ!")
                return

            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            bot_choice = random.choice(["bua", "keo", "bao"])
            choice_icons = {"bua": "👊 (Búa)", "keo": "✌️ (Kéo)", "bao": "🖐️ (Bao)"}

            if user_choice == bot_choice:
                refund = amount * 0.5
                user["balance"] += refund
                res_text = (
                    f"🤝 <b>KẾT QUẢ KÉO BÚA BAO:</b> HOÀ!\n"
                    f"• Bạn chọn: {choice_icons[user_choice]}\n"
                    f"• Bot chọn: {choice_icons[bot_choice]}\n"
                    f"💰 Hoàn lại 50% tiền cược: <b>+{refund:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            elif (user_choice == "keo" and bot_choice == "bao") or \
                 (user_choice == "bua" and bot_choice == "keo") or \
                 (user_choice == "bao" and bot_choice == "bua"):
                win_amt = amount * 1.95
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ KÉO BÚA BAO:</b> THẮNG!\n"
                    f"• Bạn chọn: {choice_icons[user_choice]}\n"
                    f"• Bot chọn: {choice_icons[bot_choice]}\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ KÉO BÚA BAO:</b> THUA!\n"
                    f"• Bạn chọn: {choice_icons[user_choice]}\n"
                    f"• Bot chọn: {choice_icons[bot_choice]}\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>bua [tiền/all]</code>, <code>keo [tiền/all]</code>, <code>bao [tiền/all]</code>")
        return

    # GAME CỨU THƯƠNG
    if cmd == "cuu":
        if len(parts) >= 2:
            amount = parse_bet_amount(parts[1], user["balance"], min_amount=10000.0)
            if amount is None or amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Cứu Thương là 10,000đ hoặc số dư không đủ!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            res = random.choice(["do", "khong_do", "khong_do"])
            if res == "do":
                win_amt = amount * 3.5
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ CỨU THƯƠNG:</b> THẮNG!\n"
                    f"🚑 Xe cứu thương bị ĐỔ!\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b> (x3,5)\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ CỨU THƯƠNG:</b> THUA!\n"
                    f"🚑 Xe cứu thương KHÔNG ĐỔ!\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>cuu [tiền/all]</code>")
        return

    # GAME ĐÈN ĐỎ ĐÈN XANH
    if cmd == "vuot":
        if len(parts) >= 2:
            amount = parse_bet_amount(parts[1], user["balance"], min_amount=10000.0)
            if amount is None or amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Đèn Đỏ Đèn Xanh là 10,000đ hoặc số dư không đủ!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            res = random.choice(["vuot", "dung"])
            if res == "vuot":
                win_amt = amount * 2.2
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ ĐÈN ĐỎ ĐÈN XANH:</b> THẮNG!\n"
                    f"🚙 Xe đã VƯỢT thành công!\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b> (x2,2)\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ ĐÈN ĐỎ ĐÈN XANH:</b> THUA!\n"
                    f"🚙 Xe bị DỪNG lại!\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>vuot [tiền/all]</code>")
        return

    # GAME RÓT RƯỢU
    if cmd == "rot":
        if len(parts) >= 2:
            amount = parse_bet_amount(parts[1], user["balance"], min_amount=10000.0)
            if amount is None or amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Rót Rượu là 10,000đ hoặc số dư không đủ!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            outcome = random.choices(["day", "khong_day", "tran"], weights=[0.4, 0.58, 0.02])[0]
            if outcome == "day":
                win_amt = amount * 2.5
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ RÓT RƯỢU:</b> THẮNG!\n"
                    f"🍷 Rót rượu ĐẦY CỐC!\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b> (x2,5)\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            elif outcome == "tran":
                win_amt = amount * 99.0
                user["balance"] += win_amt
                res_text = (
                    f"🏺💥 <b>NỔ HŨ RÓT RƯỢU:</b> ĐẠI THẮNG!\n"
                    f"🍷 Rót rượu TRÀN CỐC! Trúng Nổ Hũ!\n"
                    f"💰 Tiền thưởng khủng: <b>+{win_amt:,.0f} VND</b> (x99)\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ RÓT RƯỢU:</b> THUA!\n"
                    f"🍷 Rót rượu KHÔNG ĐẦY CỐC!\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>rot [tiền/all]</code>")
        return

    # GAME BẦU CUA
    bc_mapping = {
        "bau": 1, "bầu": 1,
        "tom": 2, "tôm": 2,
        "cua": 3,
        "ca": 4, "cá": 4,
        "ga": 5, "gà": 5,
        "nai": 6
    }
    bc_names = {1: "🍐 BẦU", 2: "🦐 TÔM", 3: "🦀 CUA", 4: "🐟 CÁ", 5: "🐓 GÀ", 6: "🦌 NAI"}

    if any(p in bc_mapping for p in parts[:-1]) and (parts[-1].isdigit() or parts[-1].lower() in ["all", "allin", "tattay"]):
        doors_text, amt_str = parts[:-1], parts[-1]
        selected_doors = []
        for p in doors_text:
            if p in bc_mapping and bc_mapping[p] not in selected_doors:
                selected_doors.append(bc_mapping[p])

        if not selected_doors or len(selected_doors) > 3:
            await message.reply("⚠️ Đặt từ 1 đến tối đa 3 cửa! Ví dụ: <code>bau cua ca 5000</code> atau <code>cua all</code>")
            return

        if amt_str.lower() in ["all", "allin", "tattay"]:
            amount = user["balance"] / len(selected_doors)
        else:
            try:
                amount = float(amt_str)
            except ValueError:
                return

        if amount < 2000 or amount > 300000:
            await message.reply("⚠️ Tiền cược mỗi cửa Bầu Cua từ 2,000đ đến 300,000đ!")
            return

        total_bet = amount * len(selected_doors)
        if user["balance"] < total_bet:
            await message.reply(f"❌ Số dư không đủ! Cần {total_bet:,.0f} VND cho {len(selected_doors)} cửa cược.")
            return

        user["balance"] -= total_bet
        user["total_cuoc"] += total_bet

        dice1 = random.randint(1, 6)
        dice2 = random.randint(1, 6)
        dice3 = random.randint(1, 6)
        results = [dice1, dice2, dice3]

        total_win = 0.0
        details = []

        for door in selected_doors:
            matches = results.count(door)
            if matches == 1:
                w = amount * 1.95
                total_win += w
                details.append(f"• {bc_names[door]}: Trúng 1 viên (+{w:,.0f}đ)")
            elif matches == 2:
                w = amount * 3.0
                total_win += w
                details.append(f"• {bc_names[door]}: Trúng 2 viên (+{w:,.0f}đ)")
            elif matches == 3:
                w = amount * 4.0
                total_win += w
                details.append(f"• {bc_names[door]}: Trúng 3 viên (+{w:,.0f}đ)")
            else:
                details.append(f"• {bc_names[door]}: Trượt (-{amount:,.0f}đ)")

        user["balance"] += total_win
        res_text = (
            f"🎲 <b>KẾT QUẢ BẦU CUA:</b>\n"
            f"🎲 Kết quả xúc xắc: <b>{bc_names[dice1]} | {bc_names[dice2]} | {bc_names[dice3]}</b>\n\n"
            f"<b>Chi tiết đặt cược:</b>\n" + "\n".join(details) + "\n\n"
            f"💰 Tổng thắng: <b>+{total_win:,.0f} VND</b>\n"
            f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
        )
        await message.reply(res_text)
        return

# --- HÀM MAIN VÀ KHỞI CHẠY BOT ---
async def handle_ping(request):
    return web.Response(text="Bot BTV88 Club đang hoạt động!", status=200)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    # Mở cổng web server cho Render phát hiện Port
    await start_web_server()
    
    # Khởi chạy vòng lặp tự động tung xúc xắc Tài Xỉu ngầm
    asyncio.create_task(auto_tai_xiu_loop())
    
    await set_bot_commands(bot)
    logging.info("Bot BTV88 Club đã sẵn sàng hoạt động...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
