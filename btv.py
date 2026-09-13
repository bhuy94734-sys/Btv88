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
TOKEN = "8954729214:AAGOGoidwCLUzJ_pIfkhdAy8nzjpCunwBTc"
ADMIN_ID = 8985238179
GROUP_CHAT_ID = None 

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- BIẾN TRẠNG THÁI TRÒ CHƠI & KHUYẾN MÃI ---
current_session = 105027
current_jackpot = 600000.0
recent_tai_xiu = ['T', 'X', 'T', 'X', 'T', 'X', 'T', 'X', 'T', 'X', 'T', 'X']
recent_chan_le = ['C', 'L', 'C', 'L', 'C', 'L', 'C', 'L', 'C', 'L', 'C', 'L']
game_running = True

promo_config = {"percent": 0.0, "expire_at": None}

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
        if referrer_id and referrer_id in users_db and referrer_id != user_id:
            users_db[referrer_id]["invite_count"] += 1
    return users_db[user_id]

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Mở menu chính / Hướng dẫn"),
        BotCommand(command="sodu", description="Kiểm tra số dư ví"),
        BotCommand(command="nap", description="Nạp tiền tự động / QR Code"),
        BotCommand(command="rut", description="Tạo lệnh rút tiền"),
        BotCommand(command="code", description="Nhập Giftcode nhận thưởng"),
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

# --- LỆNH ADMIN ---
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
        f"• Nạp tiền: <code>/nap 50000</code>\n"
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
async def process_game_callback(callback: types.CallbackQuery):
    await callback.answer()  # Trả lời tức thì để nút dừng xoay
    
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
            "👉 <b>Link Room tung xúc xắc:</b> https://t.me/btv88kiemtien"
        )
    elif game_code == "game_cl":
        text = (
            "⚫️ <b>GAME CHĂN LẺ</b>\n\n"
            "📌 <b>Hướng dẫn chơi:</b> Tham gia vào nhóm chat để đặt cược cùng mọi người.\n"
            "• Đặt Chẵn: <code>/C [số tiền]</code>\n"
            "• Đặt Lẻ: <code>/L [số tiền]</code>\n\n"
            "👉 <b>Link Room tung chẵn lẻ:</b> https://t.me/btv88kiemtien"
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
            "🎳 <b>GAME BOWLING CHĂN LẺ</b>\n\n"
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
            "• Chọn 👊(Búa): Thắng ✌️ - Thua 🖐️ - Hoà 👊\n"
            "• Chọn 🖐️(Bao): Thắng 👊 - Thua ✌️ - Hoà 🖐️\n"
            "• <b>Tỉ lệ trả thưởng khi thắng:</b> x1,95 số tiền cược\n"
            "• <b>Hoà:</b> Hoàn lại 50% số tiền cược\n\n"
            "📌 <b>Lệnh đặt cược:</b>\n"
            "• Chọn Búa 👊: <code>/Bua [số tiền cược]</code>\n"
            "• Chọn Kéo ✌️: <code>/Keo [số tiền cược]</code>\n"
            "• Chọn Bao 🖐️: <code>/Bao [số tiền cược]</code>\n"
            "(Cược tối thiểu 10,000đ)"
        )
    else:
        text = "Mục game đang cập nhật!"

    try:
        await callback.message.answer(text)
    except Exception as e:
        logging.error(f"Lỗi gửi tin nhắn callback: {e}")

@dp.message(Command("sodu"))
@dp.message(F.text == "💰 Số Dư")
async def cmd_sodu(message: types.Message):
    user = get_user(message.from_user.id, message.from_user.full_name)
    await message.reply(f"💰 Số dư hiện tại của bạn: <b>{user['balance']:,.0f} VND</b>")

@dp.message(Command("nap"))
@dp.message(F.text == "💳 Nạp Tiền")
async def cmd_nap(message: types.Message):
    args = message.text.split()
    amount = 50000
    if len(args) > 1 and args[1].isdigit():
        amount = int(args[1])
    
    user_id = message.from_user.id
    name = message.from_user.full_name
    username = f"@{message.from_user.username}" if message.from_user.username else name
    user = get_user(user_id, name)
    content_nap = f"NAP{user_id}{random.randint(1000,9999)}"
    
    bonus_promo = 0.0
    if promo_config["expire_at"] and datetime.now() <= promo_config["expire_at"]:
        bonus_promo = amount * (promo_config["percent"] / 100.0)
        
    total_add = amount + bonus_promo
    user["history_nap"].append(f"Nạp {amount:,.0f} VND (+KM: {bonus_promo:,.0f} VND) [{content_nap}]")
    user["total_nap"] += amount
    user["balance"] += total_add

    ref_id = user.get("referrer_id")
    if ref_id and ref_id in users_db:
        ref_bonus = amount * 0.005
        users_db[ref_id]["balance"] += ref_bonus
        users_db[ref_id]["ref_commission"] = users_db[ref_id].get("ref_commission", 0.0) + ref_bonus
        try:
            await bot.send_message(
                ref_id, 
                f"🎉 Bạn nhận được <b>{ref_bonus:,.0f} VND</b> hoa hồng (0.5%) từ giao dịch nạp tiền của <b>{name}</b>!"
            )
        except Exception:
            pass
    
    qr_caption = (
        f"💳 <b>HƯỚNG DẪN NẠP TIỀN TỰ ĐỘNG</b> 💳\n\n"
        f"📌 <b>BƯỚC 1:</b> Quét mã QR bên dưới hoặc chuyển khoản thủ công theo thông tin:\n"
        f"• Ngân hàng: <b>MB BANK</b>\n"
        f"• Số tài khoản: <code>2105200999999</code>\n"
        f"• Chủ tài khoản: <b>KHONG QUOC BAO</b>\n"
        f"• Số tiền: <b>{amount:,.0f} VND</b>\n"
        f"• Nội dung CK bắt buộc: <code>{content_nap}</code>\n\n"
        f"📌 <b>BƯỚC 2:</b> Nhập đúng <b>Nội dung chuyển khoản</b> để tiền tự động cộng vào tài khoản trong 1-3 phút.\n"
        f"⚠️ <i>Lưu ý: Chuyển sai nội dung vui lòng liên hệ Admin để hỗ trợ xử lý!</i>"
    )
    if bonus_promo > 0:
        qr_caption += f"\n\n🎁 <b>Khuyến mãi áp dụng:</b> +{promo_config['percent']}% ({bonus_promo:,.0f} VND) thành {total_add:,.0f} VND!"

    qr_url = f"https://img.vietqr.io/image/MB-2105200999999-compact.png?amount={amount}&addInfo={content_nap}&accountName=KHONG%20QUOC%20BAO"
    
    try:
        await message.answer_photo(photo=qr_url, caption=qr_caption)
    except Exception:
        await message.answer(qr_caption)

    try:
        admin_notice = (
            f"📥 <b>THÔNG BÁO NẠP TIỀN MỚI</b>\n\n"
            f"👤 Khách hàng: <b>{name}</b> ({username})\n"
            f"🆔 ID: <code>{user_id}</code>\n"
            f"💵 Số tiền: <b>{amount:,.0f} VND</b>\n"
            f"🎁 Cộng Khuyến mãi: <b>{bonus_promo:,.0f} VND</b>\n"
            f"📝 Nội dung: <code>{content_nap}</code>"
        )
        await bot.send_message(ADMIN_ID, admin_notice)
    except Exception as e:
        logging.error(f"Không thể gửi thông báo cho Admin: {e}")

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
        await bot.send_message(ADMIN_ID, admin_notice)
    except Exception as e:
        logging.error(f"Không thể gửi thông báo cho Admin: {e}")

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
        "<b>CSKH:</b> @Miutea88"
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
            
        if text.startswith(("/tai", "/xiu", "/c", "/l", "/chan", "/le")):
            if len(parts) >= 2 and parts[1].isdigit():
                cmd = parts[0].replace("/", "")
                amount = float(parts[1])
                
                if amount < 1000: return
                if user["balance"] < amount:
                    await message.reply(f"❌ {name}, tài khoản không đủ tiền cược!")
                    return
                    
                bet_type = "tai" if cmd == "tai" else ("xiu" if cmd == "xiu" else ("chan" if cmd in ["c", "chan"] else "le"))
                user["balance"] -= amount
                user["total_cuoc"] += amount
                bets_current[user_id] = {"type": bet_type, "amount": amount, "name": name}
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

            dice_msg = await bot.send_dice(chat_id=message.chat.id, emoji="🎳")
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
                    f"🎳 Bạn chọn {bet_choice.upper()} - Đã trúng kết quả!\n"
                    f"💰 Tiền thưởng: <b>+{win_amt:,.0f} VND</b>\n"
                    f"💵 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                )
            else:
                res_text = (
                    f"❌ <b>KẾT QUẢ BOWLING ({pins} chai):</b> THUA!\n"
                    f"🎳 Kết quả không khớp cược của bạn!\n"
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
    global current_session, current_jackpot, recent_tai_xiu, recent_chan_le, bets_current, GROUP_CHAT_ID
    
    logging.info("⏳ Đang khởi tạo Vòng lặp trò chơi...")
    await asyncio.sleep(5)
    
    while game_running:
        try:
            if not GROUP_CHAT_ID:
                await asyncio.sleep(3)
                continue

            bets_current.clear()
            await unlock_chat(GROUP_CHAT_ID)
            
            tx_display = " ".join(["🔵" if x == 'T' else "🔴" for x in recent_tai_xiu[-12:]])
            cl_display = " ".join(["⚪" if x == 'C' else "⚫" for x in recent_chan_le[-12:]])
            
            start_text = (
                f"🟢 <b>BẮT ĐẦU PHIÊN MỚI (#{current_session})</b>\n\n"
                f"⏳ <b>Thời gian đặt cược: 40 giây</b>\n"
                f"💰 <b>Hũ Jackpot: {current_jackpot:,.0f} VND</b>\n\n"
                f"📊 <b>THỐNG KÊ 12 PHIÊN GẦN NHẤT:</b>\n"
                f"• Tài / Xỉu: {tx_display}\n"
                f"• Chẵn / Lẻ: {cl_display}\n\n"
                f"👇 <i>Cú pháp cược:</i> <code>/Tai 10000</code> | <code>/Xiu 10000</code>"
            )
            
            session_msg = await bot.send_message(GROUP_CHAT_ID, start_text)
            
            for remaining in range(35, 0, -5):
                await asyncio.sleep(5)
                total_t = sum(b["amount"] for b in bets_current.values() if b["type"] == "tai")
                total_x = sum(b["amount"] for b in bets_current.values() if b["type"] == "xiu")
                
                update_text = (
                    f"🟢 <b>PHIÊN (#{current_session}) - ĐANG NHẬN CƯỢC</b>\n\n"
                    f"⏳ Còn lại: <b>{remaining} giây</b>\n"
                    f"💰 Tổng cược Tài: <b>{total_t:,.0f}</b> | Xỉu: <b>{total_x:,.0f}</b>\n"
                    f"💎 Hũ: <b>{current_jackpot:,.0f} VND</b>\n\n"
                    f"👉 Cú pháp: <code>/Tai [tiền]</code> | <code>/Xiu [tiền]</code>"
                )
                try:
                    await session_msg.edit_text(update_text)
                except Exception:
                    pass
                    
            await asyncio.sleep(5)
            
            await lock_chat(GROUP_CHAT_ID)
            try:
                await session_msg.edit_text(f"🔒 <b>PHIÊN (#{current_session}) ĐÃ ĐÓNG CƯỢC. ĐANG QUAY THƯỞNG...</b>")
            except Exception:
                pass
                
            await asyncio.sleep(1)
            
            d1 = (await bot.send_dice(GROUP_CHAT_ID, emoji="🎲")).dice.value
            await asyncio.sleep(1)
            d2 = (await bot.send_dice(GROUP_CHAT_ID, emoji="🎲")).dice.value
            await asyncio.sleep(1)
            d3 = (await bot.send_dice(GROUP_CHAT_ID, emoji="🎲")).dice.value
            await asyncio.sleep(2)
            
            total_points = d1 + d2 + d3
            is_tai = total_points >= 11
            tx_result = "Tài" if is_tai else "Xỉu"
            cl_result = "Chẵn" if total_points % 2 == 0 else "Lẻ"
            
            recent_tai_xiu.append('T' if is_tai else 'X')
            recent_chan_le.append('C' if total_points % 2 == 0 else 'L')
            
            total_win_money = 0
            total_lose_money = 0
            
            for uid, bet in bets_current.items():
                b_type, b_amt = bet["type"], bet["amount"]
                user = get_user(uid)
                won = False
                if b_type == "tai" and is_tai: won = True
                elif b_type == "xiu" and not is_tai: won = True
                elif b_type == "chan" and total_points % 2 == 0: won = True
                elif b_type == "le" and total_points % 2 != 0: won = True
                
                if won:
                    payout = b_amt * 0.95
                    win_total = payout + b_amt
                    user["balance"] += win_total
                    total_win_money += payout
                    
                    try:
                        pm_win = (
                            f"🎉 <b>THÔNG BÁO THẮNG CƯỢC PHIÊN #{current_session}</b> 🎉\n\n"
                            f"🎲 Kết quả: <b>{d1}-{d2}-{d3}</b> ({total_points} điểm - {tx_result})\n"
                            f"🎯 Bạn chọn: <b>{b_type.upper()}</b>\n"
                            f"💰 Tiền cược: <b>{b_amt:,.0f} VND</b>\n"
                            f"💵 Số tiền thưởng nhận được: <b>+{payout:,.0f} VND</b>\n"
                            f"💳 Số dư hiện tại: <b>{user['balance']:,.0f} VND</b>"
                        )
                        await bot.send_message(uid, pm_win)
                    except Exception:
                        pass
                else:
                    total_lose_money += b_amt
                    try:
                        pm_lose = (
                            f"❌ <b>THÔNG BÁO KẾT QUẢ PHIÊN #{current_session}</b> ❌\n\n"
                            f"🎲 Kết quả: <b>{d1}-{d2}-{d3}</b> ({total_points} điểm - {tx_result})\n"
                            f"🎯 Bạn chọn: <b>{b_type.upper()}</b>\n"
                            f"💸 Số tiền đã thua: <b>-{b_amt:,.0f} VND</b>\n"
                            f"💳 Số dư còn lại: <b>{user['balance']:,.0f} VND</b>"
                        )
                        await bot.send_message(uid, pm_lose)
                    except Exception:
                        pass
                    
            current_jackpot += total_lose_money * 0.01
            
            tx_display_res = " ".join(["🔵" if x == 'T' else "🔴" for x in recent_tai_xiu[-12:]])
            cl_display_res = " ".join(["⚪" if x == 'C' else "⚫" for x in recent_chan_le[-12:]])
            
            result_text = (
                f"🔒 <b>KẾT QUẢ PHIÊN (#{current_session})</b>\n\n"
                f"🎲 Xúc xắc: <b>{d1} - {d2} - {d3}</b> ➔ <b>{total_points} điểm</b> ➔ <b>{tx_result} | {cl_result}</b>\n\n"
                f"| 💰 TỔNG THẮNG: {total_win_money:,.0f} VND\n"
                f"| 💸 TỔNG THUA: {total_lose_money:,.0f} VND\n"
                f"| 🏺 HŨ HIỆN TẠI: {current_jackpot:,.0f} VND\n\n"
                f"📊 <b>THỐNG KÊ TÀI XỈU:</b>\n{tx_display_res}\n\n"
                f"📊 <b>CHẴN LẺ:</b>\n{cl_display_res}"
            )
            
            await bot.send_message(GROUP_CHAT_ID, result_text)
            current_session += 1
            await asyncio.sleep(4)
            
        except Exception as e:
            logging.error(f"Lỗi game loop: {e}")
            await asyncio.sleep(5)

# --- SERVER WEB UPTIME ---
async def handle_ping(request):
    return web.Response(text="BTV88 Bot Active", status=200)

async def main():
    await set_bot_commands(bot)
    
    app = web.Application()
    app.router.add_get("/", handle_ping)
    
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    
    asyncio.create_task(game_loop())
    asyncio.create_task(auto_code_loop())
    
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
