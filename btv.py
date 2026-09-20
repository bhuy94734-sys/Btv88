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
from aiohttp import web

# --- CẤU HÌNH CƠ BẢN ---
TOKEN = "8905955749:AAGmfbtPR0jmox3sMW3t84nK09QMq4SLiyY"
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
recent_tai_xiu = ['T', 'X', 'T', 'X', 'T', 'X', 'T', 'X', 'T', 'X', 'T', 'X']
recent_chan_le = ['C', 'L', 'C', 'L', 'C', 'L', 'C', 'L', 'C', 'L', 'C', 'L']
game_running = True

promo_config = {"percent": 0.0, "expire_at": None}

# Biến bổ sung cho tính năng mới
force_result = None  # Cờ ép kết quả: 'tai' hoặc 'xiu'

# Biến bổ sung cho game Máy Bay Aviator
aviator_games = {}

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
        "ref_commission": 0.0,
        "aviator_bet_count": 0,
        "aviator_history": []
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
            "ref_commission": 0.0,
            "aviator_bet_count": 0,
            "aviator_history": []
        }
        if referrer_id and referrer_id in users_db and referrer_id != user_id:
            users_db[referrer_id]["invite_count"] += 1
    if "aviator_bet_count" not in users_db[user_id]:
        users_db[user_id]["aviator_bet_count"] = 0
    if "aviator_history" not in users_db[user_id]:
        users_db[user_id]["aviator_history"] = []
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
        [InlineKeyboardButton(text="Bầu Cua 🦀", callback_data="game_bau_cua"), InlineKeyboardButton(text="Máy Bay Avitor🛩️", callback_data="game_aviator")],
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

@dp.message(Command("taocode"))
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

@dp.message(Command("tao_code"))
async def cmd_admin_tao_code(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 4:
        await message.reply("⚠️ Cú pháp: <code>/tao_code [Mã_Code] [Số_tiền] [Số_lượt]</code>")
        return
    code = args[1].upper()
    try:
        amount = float(args[2])
        uses = int(args[3])
        active_codes[code] = {"amount": amount, "uses": uses, "expire_at": None}
        await message.reply(f"🎁 Đã tạo Giftcode <b>{code}</b>: <b>{amount:,.0f} VND</b> ({uses} lượt dùng)")
    except ValueError:
        await message.reply("❌ Số tiền hoặc số lượt không hợp lệ!")

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

# --- LỆNH XEM DANH SÁCH LỆNH CỦA NGƯỜI CHƠI ---
@dp.message(Command("lenh"))
async def cmd_user_lenh(message: types.Message):
    text = (
        f"📜 <b>DANH SÁCH LỆNH DÀNH CHO NGƯỜI CHƠI</b>\n\n"
        f"🎲 <b>CƯỢC TÀI XỈU - CHẮN LẺ (TRONG NHÓM):</b>\n"
        f"<b>Cược công khai:</b>\n"
        f"• Lệnh cược Tài: <code>/Tai (số tiền cược)</code>\n"
        f"• Lệnh cược Xỉu: <code>/Xiu (số tiền cược)</code>\n"
        f"• Lệnh cược Chẵn: <code>/C (số tiền cược)</code>\n"
        f"• Lệnh cược Lẻ: <code>/L (số tiền cược)</code>\n"
        f"<b>Cược ẩn danh:</b>\n"
        f"• Lệnh cược Tài ẩn danh: <code>/TT (số tiền cược)</code>\n"
        f"• Lệnh cược Xỉu ẩn danh: <code>/XX (số tiền cược)</code>\n"
        f"• Lệnh cược Chẵn ẩn danh: <code>/CC (số tiền cược)</code>\n"
        f"• Lệnh cược Lẻ ẩn danh: <code>/LL (số tiền cược)</code>\n\n"
        f"💳 <b>TÀI KHOẢN & GIAO DỊCH:</b>\n"
        f"• <code>/start</code> - Khởi động bot & mở menu chính\n"
        f"• <code>/sodu</code> - Kiểm tra số dư tài khoản\n"
        f"• <code>/nap</code> - Tạo lệnh nạp tiền\n"
        f"• <code>/rut (số tiền) (STK) (Ngân hàng)</code> - Rút tiền về ngân hàng\n"
        f"• <code>/code (MãCode)</code> - Nhập Giftcode nhận thưởng\n"
        f"• <code>/lenh</code> - Xem danh sách tất cả các lệnh người chơi\n\n"
        f"🎮 <b>CÚ PHÁP CÁC GAME KHÁC:</b>\n"
        f"• Bỏng ngô: <code>/Ngo (số tiền)</code>\n"
        f"• Bóng rổ: <code>/BR (số tiền)</code>\n"
        f"• Bóng đá: <code>/BD (số tiền)</code>\n"
        f"• Bowling: <code>/Chan (số tiền)</code> | <code>/Le (số tiền)</code>\n"
        f"• Phi tiêu: <code>/vong1</code> đến <code>/vong5 (số tiền)</code>\n"
        f"• Kéo búa bao: <code>/Bua</code> | <code>/Keo</code> | <code>/Bao (số tiền)</code>\n"
        f"• Cứu thương: <code>/cuu (số tiền)</code>\n"
        f"• Đèn đỏ đèn xanh: <code>/vuot (số tiền)</code>\n"
        f"• Rót rượu: <code>/rot (số tiền)</code>\n"
        f"• Bầu cua: <code>[Cửa1] [Cửa2] [Cửa3] (số tiền)</code>\n"
        f"• Máy Bay Aviator: <code>/Bay (số tiền cược)</code>"
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
        f"📜 <b>HƯỚNG DẪN CƯỢC NHANH TRONG NHÓM:</b>\n"
        f"• Đặt Tài: <code>/Tai 10000</code>\n"
        f"• Đặt Xỉu: <code>/Xiu 10000</code>\n"
        f"• Đặt Chẵn: <code>/C 10000</code>\n"
        f"• Đặt Lẻ: <code>/L 10000</code>\n\n"
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
            "📌 <b>Hướng dẫn chơi:</b> Tham gia vào nhóm chat để đặt cược cùng mọi người.\n"
            "• Đặt Tài: <code>/Tai [số tiền]</code>\n"
            "• Đặt Xỉu: <code>/Xiu [số tiền]</code>\n\n"
            "👉 <b>Link Room tung xúc xắc:</b> https://t.me/btv88club"
        )
    elif game_code == "game_cl":
        text = (
            "⚫️ <b>GAME CHĂN LẺ</b>\n\n"
            "📌 <b>Hướng dẫn chơi:</b> Tham gia vào nhóm chat để đặt cược cùng mọi người.\n"
            "• Đặt Chẵn: <code>/C [số tiền]</code>\n"
            "• Đặt Lẻ: <code>/L [số tiền]</code>\n\n"
            "👉 <b>Link Room tung chẵn lẻ:</b> https://t.me/btv88club"
        )
    elif game_code == "game_ngo":
        text = (
            "🍿 <b>GAME BỎNG NGÔ</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "• Ngô Đổ Tràn Ra Ngoài Là <b>THUA</b>\n"
            "• Ngô Không Tràn Ra Ngoài Là <b>THẮNG</b>\n"
            "• <b>Tỉ lệ trả thưởng:</b> Thắng x8,5 SỐ TIỀN CƯỢC\n\n"
            "📌 <b>Lệnh đặt cược:</b> <code>/Ngo [số tiền cược]</code> (Cược tối thiểu 20,000đ)"
        )
    elif game_code == "game_br":
        text = (
            "🏀 <b>GAME BÓNG RỔ</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "• Tung Bóng Vào Rổ Là <b>THẮNG</b>\n"
            "• Tung Bóng Ra Ngoài Là <b>THUA</b>\n"
            "• <b>Tỉ lệ trả thưởng:</b> x1,90 số tiền cược\n\n"
            "📌 <b>Lệnh đặt cược:</b> <code>/BR [số tiền cược]</code> (Cược tối thiểu 10,000đ)"
        )
    elif game_code == "game_bd":
        text = (
            "⚽️ <b>GAME BÓNG ĐÁ</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "• Sút Vào Gôn Là <b>THẮNG</b>\n"
            "• Sút Ra Ngoài Là <b>THUA</b>\n"
            "• <b>Tỉ lệ trả thưởng:</b> x1,5 số tiền cược\n\n"
            "📌 <b>Lệnh đặt cược:</b> <code>/BD [số tiền cược]</code> (Cược tối thiểu 10,000đ)"
        )
    elif game_code == "game_bw":
        text = (
            " bowling CHĂN LẺ</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "• Ném bóng đổ 2,4,6 chai là <b>CHẲN</b>\n"
            "• Ném bóng đổ 1,3,5 chai là <b>LẺ</b>\n"
            "• Ném ra ngoài là <b>THUA</b>\n"
            "• <b>Tỉ lệ trả thưởng:</b> x1,90 số tiền cược\n\n"
            "📌 <b>Lệnh đặt cược:</b>\n"
            "• Cược Chẵn: <code>/Chan [số tiền cược]</code>\n"
            "• Cược Lẻ: <code>/Le [số tiền cược]</code>\n"
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
            "📌 <b>Lệnh đặt cược:</b>\n"
            "• Vòng 1: <code>/vong1 [số tiền cược]</code>\n"
            "• Vòng 2: <code>/vong2 [số tiền cược]</code>\n"
            "• Vòng 3: <code>/vong3 [số tiền cược]</code>\n"
            "• Vòng 4: <code>/vong4 [số tiền cược]</code>\n"
            "• Vòng 5: <code>/vong5 [số tiền cược]</code>\n"
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
            "📌 <b>Lệnh đặt cược:</b>\n"
            "• Chọn Búa 👊: <code>/Bua [số tiền cược]</code>\n"
            "• Chọn Kéo ✌️: <code>/Keo [số tiền cược]</code>\n"
            "• Chọn Bao 🖐️: <code>/Bao [số tiền cược]</code>\n"
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
            "Lệnh đặt cược: <code>/cuu (số tiền cược)</code>"
        )
    elif game_code == "game_den_do_den_xanh":
        text = (
            "🚙 <b>GAME ĐÈN ĐỎ ĐÈN XANH</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "Xe Vượt đèn Đỏ là Thắng (X2,2 số tiền cược)\n"
            "Xe Dừng đèn Đỏ là Thua\n\n"
            "Lệnh đặt cược: <code>/vuot (số tiền cược)</code>"
        )
    elif game_code == "game_rot_ruou":
        text = (
            "🍷 <b>GAME RÓT RƯỢU</b>\n\n"
            "<b>Hướng dẫn chơi:</b>\n"
            "Rót rượu đầy cốc là Thắng (x2,5 số tiền cược)\n"
            "Rót rượu không đầy cốc là Thua\n"
            "Rót rượu tràn ra khỏi cốc là Nổ Hũ (x99 số tiền cược)\n\n"
            "Lệnh đặt cược: <code>/rot (số tiền cược)</code>"
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
            "👉 Cách chơi: [cửa 1] [cửa 2] [cửa 3] [tiền cược]\n"
            "VD: <code>BAU CUA CA 5000</code> hoặc <code>CUA 10000</code>"
        )
    elif game_code == "game_aviator":
        user = get_user(callback.from_user.id, callback.from_user.full_name)
        history_str = "Chưa có dữ liệu"
        if user["aviator_history"]:
            history_str = "\n".join([f"• Phiên {item['session']}: Cược {item['bet']:,.0f}đ - Hệ số x{item['target_x']:.2f} - Kết quả: {item['result']}" for item in user["aviator_history"][-5:]])
        text = (
            "🛩️ <b>MÁY BAY AVIATOR</b> 🛩️\n\n"
            "<b>Mô tả game:</b>\n"
            "Máy Bay ✈️ - Bay càng cao X càng lớn ✅\n\n"
            "📊 <b>Thống kê các phiên bay & hệ số bay đã từng đặt cược:</b>\n"
            f"{history_str}\n\n"
            "📌 <b>Lệnh đặt cược:</b> <code>/Bay (số tiền cược)</code>"
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
            f"📥 <b>YÊU CẦU NẠP TIỀN MỚI DẦN DỰYỆT</b>\n\n"
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

        # Bổ sung thông báo nạp thành công lên nhóm chat
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

    # Bổ sung bàn phím duyệt rút tiền cho Admin và thông báo tự động
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
        await message.reply("❌ Mã Giftcode này đã quá thời gian sử dụng (3 phút)!")
        return

    if gift["uses"] <= 0:
        del active_codes[code]
        await message.reply("❌ Mã Giftcode này đã được sử dụng!")
        return

    user["balance"] += gift["amount"]
    gift["uses"] -= 1
    
    if gift["uses"] <= 0:
        del active_codes[code]

    await message.reply(f"🎁 Bạn nhận được <b>{gift['amount']:,.0f} VND</b> từ Giftcode <code>{code}</code>!")

# --- XỬ LÝ GAME MÁY BAY AVIATOR 🛩️ ---
@dp.message(Command("Bay"))
async def cmd_bay_aviator(message: types.Message):
    user_id = message.from_user.id
    name = message.from_user.full_name
    user = get_user(user_id, name)
    args = message.text.split()

    if user_id in aviator_games and aviator_games[user_id].get("running", False):
        await message.reply("⚠️ Bạn đang có một phiên bay đang diễn ra! Vui lòng hoàn tất phiên hiện tại.")
        return

    if len(args) < 2 or not args[1].replace(".", "").isdigit():
        await message.reply("⚠️ Cú pháp cược: <code>/Bay (số tiền cược)</code>")
        return

    bet_amount = float(args[1])
    if bet_amount <= 0:
        await message.reply("⚠️ Số tiền cược phải lớn hơn 0!")
        return

    if user["balance"] < bet_amount:
        await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND.")
        return

    # Trừ tiền & khoá cược
    user["balance"] -= bet_amount
    user["total_cuoc"] += bet_amount
    user["aviator_bet_count"] += 1
    count = user["aviator_bet_count"]

    # Xác định tỷ lệ random hệ số theo lần cược
    if count == 1:
        target_x = round(random.uniform(0.0, 1.85), 2)
    elif count == 2:
        target_x = round(random.uniform(0.0, 0.3), 2)
    elif count == 3:
        target_x = round(random.uniform(0.0, 0.8), 2)
    elif count == 4:
        target_x = round(random.uniform(0.0, 1.2), 2)
    elif count == 5:
        target_x = round(random.uniform(0.0, 0.6), 2)
    elif count == 6:
        target_x = round(random.uniform(0.0, 2.5), 2)
    elif count == 7:
        target_x = round(random.uniform(0.0, 0.6), 2)
    elif count == 8:
        target_x = round(random.uniform(0.0, 2.7), 2)
    elif count == 9:
        target_x = round(random.uniform(0.0, 0.6), 2)
    elif count == 10:
        target_x = round(random.uniform(0.0, 0.6), 2)
    elif count == 11:
        target_x = 0.0
    elif count == 12:
        target_x = 0.0
    elif count == 13:
        target_x = round(random.uniform(0.0, 15.0), 2)
        user["aviator_bet_count"] = 0  # Quay lại từ đầu sau lần 13
    else:
        target_x = round(random.uniform(0.0, 1.85), 2)

    # Tung icon máy bay & thông báo bắt đầu bay
    await message.reply("✈️")
    start_msg = await message.reply(f"🚀 <b>MÁY BAY BẮT ĐẦU BAY!</b> 🚀\n💰 Số tiền cược: <b>{bet_amount:,.0f} VND</b>\n🔒 Đã khoá cược thành công!")

    stop_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🛑 DỪNG BAY", callback_data=f"aviator_stop_{user_id}")]
    ])

    flight_msg = await message.reply(f"🛩️ <b>Hệ số hiện tại:</b> x0.00", reply_markup=stop_kb)

    aviator_games[user_id] = {
        "running": True,
        "bet": bet_amount,
        "target_x": target_x,
        "current_x": 0.0,
        "stopped": False,
        "flight_msg_id": flight_msg.message_id,
        "chat_id": message.chat.id
    }

    asyncio.create_task(run_aviator_flight(user_id, bet_amount, target_x, flight_msg.message_id, message.chat.id))

async def run_aviator_flight(user_id: int, bet_amount: float, target_x: float, msg_id: int, chat_id: int):
    user = get_user(user_id)
    game_data = aviator_games.get(user_id)
    if not game_data:
        return

    current_x = 0.0
    step = 0.10 if target_x > 2.0 else 0.05
    
    while current_x < target_x and game_data["running"] and not game_data["stopped"]:
        await asyncio.sleep(0.8)
        current_x = round(current_x + step, 2)
        if current_x > target_x:
            current_x = target_x
        game_data["current_x"] = current_x

        if game_data["stopped"]:
            break

        stop_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=f"🛑 DỪNG BAY (x{current_x:.2f})", callback_data=f"aviator_stop_{user_id}")]
        ])
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"🛩️ <b>Máy bay đang bay:</b> x{current_x:.2f}\n💥 Hệ số tối đa phiên: x{target_x:.2f}",
                reply_markup=stop_kb
            )
        except Exception:
            pass

    # Kết thúc phiên bay
    if game_data["running"] and not game_data["stopped"]:
        game_data["running"] = False
        user["aviator_history"].append({
            "session": len(user["aviator_history"]) + 1,
            "bet": bet_amount,
            "target_x": target_x,
            "result": "THUA 💥"
        })
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=f"💥 <b>MÁY BAY ĐÃ NỔ / DỪNG BAY!</b> 💥\n\n"
                     f"❌ Bạn chưa kịp nhấn nút Dừng Bay trước khi máy bay dừng!\n"
                     f"📊 Hệ số phiên: <b>x{target_x:.2f}</b>\n"
                     f"💸 Bạn đã THUA <b>-{bet_amount:,.0f} VND</b>\n"
                     f"💰 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
            )
        except Exception:
            pass

@dp.callback_query(F.data.startswith("aviator_stop_"))
async def process_aviator_stop(callback: types.CallbackQuery):
    target_user_id = int(callback.data.split("_")[2])
    if callback.from_user.id != target_user_id:
        await callback.answer("⚠️ Đây không phải phiên bay của bạn!", show_alert=True)
        return

    game_data = aviator_games.get(target_user_id)
    if not game_data or not game_data["running"] or game_data["stopped"]:
        await callback.answer("⚠️ Phiên bay đã kết thúc!", show_alert=True)
        return

    game_data["stopped"] = True
    game_data["running"] = False
    
    stop_x = game_data["current_x"]
    bet_amount = game_data["bet"]
    win_amt = bet_amount * stop_x

    user = get_user(target_user_id)
    user["balance"] += win_amt

    user["aviator_history"].append({
        "session": len(user["aviator_history"]) + 1,
        "bet": bet_amount,
        "target_x": stop_x,
        "result": f"THẮNG +{win_amt:,.0f}đ (x{stop_x:.2f})"
    })

    await callback.answer(f"🎉 Bạn đã chốt hạ x{stop_x:.2f}!")

    try:
        await bot.edit_message_text(
            chat_id=game_data["chat_id"],
            message_id=game_data["flight_msg_id"],
            text=f"🎉 <b>BẠN ĐÃ DỪNG BAY THÀNH CÔNG!</b> 🎉\n\n"
                 f"🛩️ Hệ số chốt: <b>x{stop_x:.2f}</b>\n"
                 f"💰 Số tiền thưởng: <b>+{win_amt:,.0f} VND</b>\n"
                 f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
        )
    except Exception:
        pass

# --- XỬ LÝ CÁC GAME TRONG NHÓM & MINI GAME CÁ NHÂN ---
@dp.message()
async def catch_all_messages(message: types.Message):
    global GROUP_CHAT_ID
    if not message.text:
        return
        
    user_id = message.from_user.id
    name = message.from_user.full_name
    user = get_user(user_id, name)
    text = message.text.lower().strip()
    parts = text.split()

    if message.chat.type in ["group", "supergroup"]:
        if GROUP_CHAT_ID != message.chat.id:
            GROUP_CHAT_ID = message.chat.id
            
        # Bổ sung xử lý cược ẩn danh trong nhóm chat: /tt, /xx, /cc, /ll
        if text.startswith(("/tai", "/xiu", "/c", "/l", "/chan", "/le", "/tt", "/xx", "/cc", "/ll")):
            if len(parts) >= 2 and parts[1].isdigit():
                cmd = parts[0].replace("/", "")
                amount = float(parts[1])
                
                if amount < 1000: return
                if user["balance"] < amount:
                    await message.reply(f"❌ {name}, tài khoản không đủ tiền cược!")
                    return
                    
                is_anonymous = cmd in ["tt", "xx", "cc", "ll"]
                
                if cmd in ["tai", "tt"]:
                    bet_type = "tai"
                elif cmd in ["xiu", "xx"]:
                    bet_type = "xiu"
                elif cmd in ["chan", "c", "cc"]:
                    bet_type = "chan"
                else:
                    bet_type = "le"

                user["balance"] -= amount
                user["total_cuoc"] += amount
                bets_current[user_id] = {
                    "type": bet_type, 
                    "amount": amount, 
                    "name": name, 
                    "anonymous": is_anonymous
                }

                # Bổ sung thông báo tự động cho Admin khi khách cược to trên 100,000đ
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
                        f"🥷 <b>CƯỢC ẨN DANH THÀNH CÔNG</b>\n\n"
                        f"🎯 <b>Cửa cược:</b> <b>{bet_type.upper()}</b>\n"
                        f"💰 <b>Số tiền:</b> <b>{amount:,.0f} VND</b>"
                    )
                else:
                    await message.reply(f"✅ <b>{name}</b> cược <b>{amount:,.0f} VND</b> vào <b>{bet_type.upper()}</b>!")
        return

    # GAME BỎNG NGÔ
    if text.startswith("/ngo") or text.startswith("ngo"):
        if len(parts) >= 2 and parts[1].isdigit():
            amount = float(parts[1])
            if amount < 20000:
                await message.reply("⚠️ Cược tối thiểu cho game Bỏng Ngô là 20,000đ!")
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
            await message.reply("⚠️ Cú pháp: <code>/Ngo [số tiền cược]</code>")
        return

    # GAME BÓNG RỔ
    if text.startswith("/br"):
        if len(parts) >= 2 and parts[1].isdigit():
            amount = float(parts[1])
            if amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Bóng Rổ là 10,000đ!")
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
            await message.reply("⚠️ Cú pháp: <code>/BR [số tiền cược]</code>")
        return

    # GAME BÓNG ĐÁ
    if text.startswith("/bd"):
        if len(parts) >= 2 and parts[1].isdigit():
            amount = float(parts[1])
            if amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Bóng Đá là 10,000đ!")
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
            await message.reply("⚠️ Cú pháp: <code>/BD [số tiền cược]</code>")
        return

    # GAME BOWLING
    if text.startswith(("/chan", "/le")):
        if len(parts) >= 2 and parts[1].isdigit():
            bet_choice = parts[0].replace("/", "")
            amount = float(parts[1])
            if amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Bowling là 10,000đ!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            dice_msg = await bot.send_dice(chat_id=message.chat.id, emoji="Bowling")
            await asyncio.sleep(3.5)
            pins = dice_msg.dice.value
            
            is_win = False
            if pins in [2, 4, 6] and bet_choice == "chan":
                is_win = True
            elif pins in [1, 3, 5] and bet_choice == "le":
                is_win = True

            if is_win:
                win_amt = amount * 1.90
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ BOWLING ({pins} chai):</b> THẮNG!\n"
                    f" bowling Bạn chọn {bet_choice.upper()} - Đã trúng kết quả!\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ BOWLING ({pins} chai):</b> THUA!\n"
                    f" bowling Kết quả không khớp cược của bạn!\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>/Chan [số tiền]</code> hoặc <code>/Le [số tiền]</code>")
        return

    # GAME PHI TIÊU
    if text.startswith(("/vong1", "/vong2", "/vong3", "/vong4", "/vong5")):
        if len(parts) >= 2 and parts[1].isdigit():
            target_vong = int(parts[0].replace("/vong", ""))
            amount = float(parts[1])
            if amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho game Phi Tiêu là 10,000đ!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            dice_msg = await bot.send_dice(chat_id=message.chat.id, emoji="🎯")
            await asyncio.sleep(3.5)
            val = dice_msg.dice.value
            hit_vong = 0
            if val == 6: hit_vong = 1
            elif val == 5: hit_vong = 2
            elif val == 4: hit_vong = 3
            elif val == 3: hit_vong = 4
            elif val == 2: hit_vong = 5

            if hit_vong == target_vong:
                win_amt = amount * 2.0
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ PHI TIÊU:</b> THẮNG!\n"
                    f"🎯 Phi tiêu đã cắm đúng <b>Vòng {target_vong}</b>!\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                hit_info = f"Trúng Vòng {hit_vong}" if hit_vong > 0 else "Phi ra ngoài"
                res_text = (
                    f"❌ <b>KẾT QUẢ PHI TIÊU:</b> THUA!\n"
                    f"🎯 Kết quả: {hit_info} (Bạn chọn Vòng {target_vong})\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>/vong1 [số tiền]</code> đến <code>/vong5 [số tiền]</code>")
        return

    # GAME KÉO BÚA BAO
    if text.startswith(("/bua", "/keo", "/bao")):
        if len(parts) >= 2 and parts[1].isdigit():
            user_choice = parts[0].replace("/", "")
            amount = float(parts[1])
            if amount < 10000:
                await message.reply("⚠️ Cược tối thiểu cho Kéo Búa Bao là 10,000đ!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            bot_choices = ["bua", "keo", "bao"]
            bot_pick = random.choice(bot_choices)
            
            icon_map = {"bua": "👊", "keo": "✌️", "bao": "🖐️"}
            bot_icon = icon_map[bot_pick]
            user_icon = icon_map[user_choice]

            await message.reply(f"🎲 Bot đang đưa ra: <b>{bot_icon}</b> ...")
            await asyncio.sleep(1.5)

            if user_choice == bot_pick:
                refund = amount * 0.5
                user["balance"] += refund
                res_text = (
                    f"🤝 <b>KẾT QUẢ KÉO BÚA BAO: HOÀ!</b>\n"
                    f"Bạn: {user_icon} vs Bot: {bot_icon}\n"
                    f"💵 Hoàn lại 50% cược: <b>+{refund:,.0f} VND</b>\n"
                    f"💰 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            elif (user_choice == "keo" and bot_pick == "bao") or \
                 (user_choice == "bua" and bot_pick == "keo") or \
                 (user_choice == "bao" and bot_pick == "bua"):
                win_amt = amount * 1.95
                user["balance"] += win_amt
                res_text = (
                    f"🎉 <b>KẾT QUẢ KÉO BÚA BAO: THẮNG!</b>\n"
                    f"Bạn: {user_icon} vs Bot: {bot_icon}\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ KÉO BÚA BAO: THUA!</b>\n"
                    f"Bạn: {user_icon} vs Bot: {bot_icon}\n"
                    f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>/Bua [số tiền]</code> | <code>/Keo [số tiền]</code> | <code>/Bao [số tiền]</code>")
        return

    # GAME CỨU THƯƠNG (KHÁCH LUÔN THUA)
    if text.startswith("/cuu"):
        if len(parts) >= 2 and parts[1].isdigit():
            amount = float(parts[1])
            if amount <= 0:
                await message.reply("⚠️ Số tiền cược phải lớn hơn 0!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            await bot.send_message(chat_id=message.chat.id, text="🚑")
            await asyncio.sleep(2)

            res_text = (
                f"❌ <b>KẾT QUẢ CỨU THƯƠNG: THUA!</b>\n"
                f"🚑 Xe cứu thương KHÔNG ĐỔ!\n"
                f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
            )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>/cuu (số tiền cược)</code>")
        return

    # GAME ĐÈN ĐỎ ĐÈN XANH (KHÁCH LUÔN THUA)
    if text.startswith("/vuot"):
        if len(parts) >= 2 and parts[1].isdigit():
            amount = float(parts[1])
            if amount <= 0:
                await message.reply("⚠️ Số tiền cược phải lớn hơn 0!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            await bot.send_message(chat_id=message.chat.id, text="🚙")
            await asyncio.sleep(2)

            res_text = (
                f"❌ <b>KẾT QUẢ ĐÈN ĐỎ ĐÈN XANH: THUA!</b>\n"
                f"🚙 Xe đã Dừng lại trước đèn đỏ!\n"
                f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
            )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>/vuot (số tiền cược)</code>")
        return

    # GAME RÓT RƯỢU (KHÁCH LUÔN THUA)
    if text.startswith("/rot"):
        if len(parts) >= 2 and parts[1].isdigit():
            amount = float(parts[1])
            if amount <= 0:
                await message.reply("⚠️ Số tiền cược phải lớn hơn 0!")
                return
            if user["balance"] < amount:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND. Vui lòng nạp thêm!")
                return

            user["balance"] -= amount
            user["total_cuoc"] += amount

            await bot.send_message(chat_id=message.chat.id, text="🍷")
            await asyncio.sleep(2)

            res_text = (
                f"❌ <b>KẾT QUẢ RÓT RƯỢU: THUA!</b>\n"
                f"🍷 Rót rượu KHÔNG ĐẦY CỐC!\n"
                f"💸 Số tiền thua: <b>-{amount:,.0f} VND</b>\n"
                f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
            )
            await message.reply(res_text)
        else:
            await message.reply("⚠️ Cú pháp: <code>/rot (số tiền cược)</code>")
        return

    # GAME BẦU CUA
    bau_cua_map = {
        "BAU": 1, "BẦU": 1,
        "TOM": 2, "TÔM": 2,
        "CUA": 3,
        "CA": 4, "CÁ": 4,
        "GA": 5, "GÀ": 5,
        "NAI": 6
    }
    bau_cua_names = {1: "🍐 BẦU", 2: "🦐 TÔM", 3: "🦀 CUA", 4: "🐟 CÁ", 5: "🐓 GÀ", 6: "🦌 NAI"}

    raw_tokens = [t.upper() for t in parts]
    if raw_tokens and raw_tokens[-1].isdigit():
        amt = float(raw_tokens[-1])
        door_tokens = raw_tokens[:-1]
        
        valid_doors = [bau_cua_map[t] for t in door_tokens if t in bau_cua_map]
        
        if len(valid_doors) > 0 and len(valid_doors) == len(door_tokens) and len(valid_doors) <= 3:
            if amt < 2000 or amt > 300000:
                await message.reply("⚠️ Tiền cược Bầu Cua tối thiểu là 2.000đ và tối đa là 300.000đ!")
                return
            if user["balance"] < amt:
                await message.reply(f"❌ Số dư không đủ! Số dư hiện tại: {user['balance']:,.0f} VND.")
                return

            user["balance"] -= amt
            user["total_cuoc"] += amt

            d1 = (await bot.send_dice(chat_id=message.chat.id, emoji="🎲")).dice.value
            await asyncio.sleep(1)
            d2 = (await bot.send_dice(chat_id=message.chat.id, emoji="🎲")).dice.value
            await asyncio.sleep(1)
            d3 = (await bot.send_dice(chat_id=message.chat.id, emoji="🎲")).dice.value
            await asyncio.sleep(1)

            results = [d1, d2, d3]
            res_str = ", ".join([bau_cua_names[r] for r in results])

            total_win = 0.0
            win_details = []

            for door in set(valid_doors):
                match_count = results.count(door)
                if match_count == 1:
                    win_amt = amt * 1.95
                    total_win += win_amt
                    win_details.append(f"{bau_cua_names[door]} (x1): +{win_amt:,.0f} VND")
                elif match_count == 2:
                    win_amt = amt * 3.0
                    total_win += win_amt
                    win_details.append(f"{bau_cua_names[door]} (x2): +{win_amt:,.0f} VND")
                elif match_count == 3:
                    win_amt = amt * 4.0
                    total_win += win_amt
                    win_details.append(f"{bau_cua_names[door]} (x3): +{win_amt:,.0f} VND")

            user["balance"] += total_win

            if total_win > 0:
                detail_str = "\n".join(win_details)
                res_text = (
                    f"🎉 <b>KẾT QUẢ BẦU CUA: THẮNG!</b>\n\n"
                    f"🎲 Kết quả xúc xắc: <b>{res_str}</b>\n"
                    f"{detail_str}\n"
                    f"💰 Tổng tiền thắng: <b>+{total_win:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ BẦU CUA: THUA!</b>\n\n"
                    f"🎲 Kết quả xúc xắc: <b>{res_str}</b>\n"
                    f"💸 Bạn không trúng cửa nào!\n"
                    f"💸 Số tiền thua: <b>-{amt:,.0f} VND</b>\n"
                    f"💵 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                )
            await message.reply(res_text)
            return

# --- VÒNG LẬP CODE TỰ ĐỘNG ---
async def auto_code_loop():
    await asyncio.sleep(10)
    while game_running:
        try:
            if GROUP_CHAT_ID:
                generated_codes = []
                expire_time = datetime.now() + timedelta(minutes=3)
                
                for _ in range(5):
                    code_str = "BTV" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
                    rand_val = random.randint(10, 2000)
                    
                    active_codes[code_str] = {
                        "amount": float(rand_val),
                        "uses": 1,
                        "expire_at": expire_time
                    }
                    generated_codes.append(f"• <code>{code_str}</code>: <b>{rand_val:,.0f} VND</b>")
                
                code_text = (
                    f"🎁 <b>CƠN MƯA GIFTCODE MIỄN PHÍ (5 MÃ)</b> 🎁\n\n"
                    + "\n".join(generated_codes) + "\n\n"
                    f"⏰ <b>Thời gian hiệu lực:</b> Đúng <b>3 phút</b>!\n"
                    f"📌 <i>Mỗi code chỉ dùng cho 1 tài khoản duy nhất. Nhập nhanh cú pháp:</i>\n"
                    f"👉 <code>/code [Mã_Code]</code>"
                )
                await bot.send_message(GROUP_CHAT_ID, code_text)
        except Exception as e:
            logging.error(f"Lỗi tự động phát code: {e}")
            
        await asyncio.sleep(2100)

# --- VÒNG LẬP GAME TỰ ĐỘNG ---
async def game_loop():
    global current_session, current_jackpot, recent_tai_xiu, recent_chan_le, bets_current, GROUP_CHAT_ID, force_result
    
    logging.info("⏳ Đang khởi tạo Vòng lặp trò chơi...")
    await asyncio.sleep(5)
    
    while game_running:
        try:
            if not GROUP_CHAT_ID:
                await asyncio.sleep(3)
                continue

            bets_current.clear()
            await unlock_chat(GROUP_CHAT_ID)
            
            tx_display = "".join([f"[{x}]" for x in recent_tai_xiu[-10:]])
            cl_display = "".join([f"[{x}]" for x in recent_chan_le[-10:]])
            
            start_msg = (
                f"🎲 <b>BẮT ĐẦU PHIÊN #{current_session}</b> 🎲\n\n"
                f"📊 <b>Cầu Tài Xỉu gần đây:</b> {tx_display}\n"
                f"📊 <b>Cầu Chẵn Lẻ gần đây:</b> {cl_display}\n"
                f"🏺 <b>Hũ Jackpot:</b> <b>{current_jackpot:,.0f} VND</b>\n\n"
                f"⏰ <b>Thời gian đặt cược:</b> 45 GIÂY!\n"
                f"👉 Đặt Tài: <code>/Tai 10000</code> | Đặt Xỉu: <code>/Xiu 10000</code>\n"
                f"👉 Đặt Chẵn: <code>/C 10000</code> | Đặt Lẻ: <code>/L 10000</code>"
            )
            await bot.send_message(GROUP_CHAT_ID, start_msg)
            
            await asyncio.sleep(30)
            
            await bot.send_message(GROUP_CHAT_ID, f"⚠️ <b>CẢNH BÁO:</b> Chỉ còn <b>15 GIÂY</b> để đặt cược phiên #{current_session}!")
            await asyncio.sleep(15)
            
            await lock_chat(GROUP_CHAT_ID)
            await bot.send_message(GROUP_CHAT_ID, f"🔒 <b>HẾT GIỜ ĐẶT CƯỢC PHIÊN #{current_session}!</b> Đang tung xúc xắc...")
            
            dice_msg = await bot.send_dice(chat_id=GROUP_CHAT_ID, emoji="🎲")
            await asyncio.sleep(3)
            
            dice_val = dice_msg.dice.value
            
            if force_result == "tai":
                d1, d2, d3 = 4, 5, 5
                force_result = None
            elif force_result == "xiu":
                d1, d2, d3 = 1, 2, 2
                force_result = None
            else:
                d1 = random.randint(1, 6)
                d2 = random.randint(1, 6)
                d3 = random.randint(1, 6)
                
            total_point = d1 + d2 + d3
            res_tx = "TAI" if total_point >= 11 else "XIU"
            res_cl = "CHAN" if total_point % 2 == 0 else "LE"
            
            recent_tai_xiu.append(res_tx[0])
            recent_chan_le.append(res_cl[0])
            
            current_jackpot += 5000.0
            
            win_text = f"🎲 <b>KẾT QUẢ PHIÊN #{current_session}</b> 🎲\n\n"
            win_text += f"🎲 Xúc xắc: <b>{d1} - {d2} - {d3}</b> (Tổng: <b>{total_point} điểm</b>)\n"
            win_text += f"🎯 Kết quả: <b>{res_tx}</b> | <b>{res_cl}</b>\n\n"
            win_text += f"🏆 <b>DANH SÁCH THẮNG CƯỢC:</b>\n"
            
            has_winner = False
            for uid, bet_info in bets_current.items():
                u_type = bet_info["type"]
                u_amt = bet_info["amount"]
                u_name = bet_info["name"]
                is_anon = bet_info.get("anonymous", False)
                display_name = "🥷 Người chơi ẩn danh" if is_anon else f"<b>{u_name}</b>"
                
                is_win = False
                if u_type == "tai" and res_tx == "TAI": is_win = True
                elif u_type == "xiu" and res_tx == "XIU": is_win = True
                elif u_type == "chan" and res_cl == "CHAN": is_win = True
                elif u_type == "le" and res_cl == "LE": is_win = True
                
                if is_win:
                    has_winner = True
                    win_money = u_amt * 1.95
                    users_db[uid]["balance"] += win_money
                    win_text += f"• {display_name}: +<b>{win_money:,.0f} VND</b> ({u_type.upper()})\n"
                    
            if not has_winner:
                win_text += "• Không có người chơi nào thắng cược phiên này.\n"
                
            await bot.send_message(GROUP_CHAT_ID, win_text)
            
            current_session += 1
            await asyncio.sleep(10)
            
        except Exception as e:
            logging.error(f"Lỗi game loop: {e}")
            await asyncio.sleep(5)

# --- KHỞI CHẠY BOT ---
async def main():
    await set_bot_commands(bot)
    asyncio.create_task(game_loop())
    asyncio.create_task(auto_code_loop())
    logging.info("🚀 Bot BTV88 Club đã sẵn sàng hoạt động!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
