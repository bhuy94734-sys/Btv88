import asyncio
import logging
import os
import random
from aiogram import Bot, Dispatcher, F, types
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    BotCommand,
    BotCommandScopeDefault,
    ChatPermissions,
)
from aiohttp import web

# --- CẤU HÌNH CƠ BẢN ---
TOKEN = os.getenv("BOT_TOKEN", "8954729214:AAGM9__IwcWXqw0duQ5gPXLv-H6BvEsal0g")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8985238179"))
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID", "-1004332420009"))

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- BIẾN TRẠNG THÁI TRÒ CHƠI ---
current_session = 105025
current_jackpot = 350000.0
recent_tai_xiu = ['T', 'X', 'T', 'X', 'T', 'X', 'T', 'X', 'T', 'X', 'T', 'X']
recent_chan_le = ['C', 'L', 'C', 'L', 'C', 'L', 'C', 'L', 'C', 'L', 'C', 'L']
game_running = True

# Cơ sở dữ liệu giả lập trong RAM
users_db = {
    ADMIN_ID: {"balance": 10000000.0, "name": "Admin Tổng"}
}
bets_current = {} # {user_id: {"type": "tai/xiu/chan/le", "amount": 10000, "name": "..."}}
active_codes = {} # {"CODE123": {"amount": 50000, "uses": 5}}

def get_user(user_id: int, name: str = "Thành viên"):
    if user_id not in users_db:
        users_db[user_id] = {"balance": 50000.0, "name": name} # Tặng vốn khởi nghiệp 50k
    return users_db[user_id]

# --- THIẾT LẬP MENU LỆNH (NÚT ≡ Menu TRÊN TELEGRAM) ---
async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Mở menu chính / Hướng dẫn"),
        BotCommand(command="sodu", description="Kiểm tra số dư ví"),
        BotCommand(command="nap", description="Nạp tiền tự động / QR Code"),
        BotCommand(command="rut", description="Tạo lệnh rút tiền"),
        BotCommand(command="code", description="Nhập Giftcode nhận thưởng"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    
    admin_commands = commands + [
        BotCommand(command="cong", description="[Admin] Cộng tiền: /cong số_tiền id"),
        BotCommand(command="tru", description="[Admin] Trừ tiền: /tru số_tiền id"),
        BotCommand(command="taocode", description="[Admin] Tạo mã: /taocode code tiền lượt"),
        BotCommand(command="thongbao", description="[Admin] Gửi thông báo toàn server"),
    ]
    try:
        await bot.set_my_commands(admin_commands, scope=types.BotCommandScopeChat(chat_id=ADMIN_ID))
    except Exception:
        pass

# --- BẢNG PHÍM MENU BẤM NHANH DƯỚI KHUNG CHAT ---
main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💰 Số Dư"), KeyboardButton(text="💳 Nạp Tiền")],
        [KeyboardButton(text="💸 Rút Tiền"), KeyboardButton(text="🎁 Nhập Code")]
    ],
    resize_keyboard=True
)

# --- HÀM KHÓA / MỞ KHÓA CHAT NHÓM ---
async def lock_chat(chat_id: int):
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(
                can_send_messages=False,
                can_send_polls=False,
                can_send_other_messages=False,
                can_add_web_page_previews=False
            )
        )
    except Exception as e:
        logging.error(f"Lỗi khóa chat: {e}")

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
        logging.error(f"Lỗi mở khóa chat: {e}")

# --- CÁC LỆNH NGƯỜI DÙNG ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    get_user(message.from_user.id, message.from_user.full_name)
    text = (
        f"💎 <b>BTV88 CLUB - CỔNG GAME TÀI XỈU UY TÍN</b> 💎\n\n"
        f"Chào mừng <b>{message.from_user.full_name}</b> đến với hệ thống tự động!\n\n"
        f"📜 <b>HƯỚNG DẪN CƯỢC NHANH TRONG NHÓM:</b>\n"
        f"• Đặt Tài: <code>/Tai 10000</code> hoặc <code>/tai 10000</code>\n"
        f"• Đặt Xỉu: <code>/Xiu 10000</code> hoặc <code>/xiu 10000</code>\n"
        f"• Đặt Chẵn: <code>/C 10000</code> hoặc <code>/chan 10000</code>\n"
        f"• Đặt Lẻ: <code>/L 10000</code> hoặc <code>/le 10000</code>\n\n"
        f"💳 <b>LỆNH GIAO DỊCH:</b>\n"
        f"• Kiểm tra ví: <code>/sodu</code>\n"
        f"• Nạp tiền: <code>/nap 50000</code>\n"
        f"• Rút tiền: <code>/rut 200000 [SốTK] [NgânHàng]</code>\n"
        f"• Nhập Code: <code>/code [MãCode]</code>"
    )
    await message.answer(text, reply_markup=main_menu_kb)

@dp.message(Command("sodu"))
async def cmd_sodu(message: types.Message):
    user = get_user(message.from_user.id, message.from_user.full_name)
    await message.reply(f"💰 Số dư hiện tại của bạn: <b>{user['balance']:,.0f} VND</b>")

@dp.message(Command("nap"))
async def cmd_nap(message: types.Message):
    args = message.text.split()
    amount = 50000
    if len(args) > 1 and args[1].isdigit():
        amount = int(args[1])
    
    user_id = message.from_user.id
    name = message.from_user.full_name
    get_user(user_id, name)
    
    content_nap = f"NAP{user_id}{random.randint(1000,9999)}"
    
    qr_caption = (
        f"🏦 <b>MÃ QR CHUYỂN KHOẢN TỰ ĐỘNG</b>\n\n"
        f"• Ngân hàng: <b>MB BANK</b>\n"
        f"• Số tài khoản: <code>2105200999999</code>\n"
        f"• Chủ tài khoản: <b>KHONG QUOC BAO</b>\n"
        f"• Số tiền: <b>{amount:,.0f} VND</b>\n"
        f"• Nội dung chuyển khoản: <code>{content_nap}</code>\n\n"
        f"⚠️ <i>Vui lòng dùng app ngân hàng quét mã QR hoặc chuyển đúng nội dung để hệ thống tự động duyệt!</i>"
    )
    
    qr_url = f"https://img.vietqr.io/image/MB-2105200999999-compact.png?amount={amount}&addInfo={content_nap}&accountName=KHONG%20QUOC%20BAO"
    
    try:
        await message.answer_photo(photo=qr_url, caption=qr_caption)
    except Exception:
        await message.answer(qr_caption)
        
    # GỬI THÔNG BÁO VỀ CHO ADMIN
    admin_msg = (
        f"🔔 <b>CÓ YÊU CẦU NẠP TIỀN MỚI!</b>\n\n"
        f"• Khách: {name} (ID: <code>{user_id}</code>)\n"
        f"• Số tiền yêu cầu: <b>{amount:,.0f} VND</b>\n"
        f"• Nội dung CK: <code>{content_nap}</code>\n\n"
        f"👉 Lệnh duyệt tiền nhanh cho admin:\n"
        f"<code>/cong {amount} {user_id}</code>"
    )
    try:
        await bot.send_message(ADMIN_ID, admin_msg)
    except Exception as e:
        logging.error(f"Không gửi được thông báo nạp cho admin: {e}")

@dp.message(Command("rut"))
async def cmd_rut(message: types.Message):
    args = message.text.split(maxsplit=3)
    user_id = message.from_user.id
    name = message.from_user.full_name
    user = get_user(user_id, name)
    
    if len(args) < 4:
        guide_text = (
            f"🏛️ <b>HƯỚNG DẪN RÚT TIỀN</b>\n\n"
            f"Vui lòng sử dụng cú pháp đầy đủ:\n"
            f"<code>/rut [Số tiền] [Số TK] [Ngân hàng]</code>\n\n"
            f"Ví dụ: <code>/rut 200000 2105200999999 MB</code>"
        )
        await message.reply(guide_text)
        return
    
    try:
        amount = float(args[1])
        stk = args[2]
        bank = args[3]
    except ValueError:
        await message.reply("❌ Số tiền rút không hợp lệ. Vui lòng nhập số nguyên.")
        return
        
    if amount < 50000:
        await message.reply("❌ Số tiền rút tối thiểu là 50,000 VND.")
        return
        
    if user["balance"] < amount:
        await message.reply(f"❌ Số dư của bạn không đủ! Số dư hiện tại: {user['balance']:,.0f} VND")
        return
        
    user["balance"] -= amount
    await message.reply(f"✅ Đã tạo yêu cầu rút <b>{amount:,.0f} VND</b> về TK <code>{stk} ({bank})</code> thành công! Vui lòng chờ Admin chuyển khoản.")
    
    admin_alert = (
        f"💸 <b>CÓ YÊU CẦU RÚT TIỀN!</b>\n\n"
        f"• Khách: {name} (ID: <code>{user_id}</code>)\n"
        f"• Số tiền: <b>{amount:,.0f} VND</b>\n"
        f"• Số tài khoản: <code>{stk}</code>\n"
        f"• Ngân hàng: <b>{bank}</b>\n\n"
        f"Nếu từ chối/hoàn tiền, dùng lệnh: <code>/cong {amount} {user_id}</code>"
    )
    try:
        await bot.send_message(ADMIN_ID, admin_alert)
    except Exception as e:
        logging.error(f"Lỗi gửi thông báo rút cho admin: {e}")

@dp.message(Command("code"))
async def cmd_code(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠️ Vui lòng nhập mã giftcode: <code>/code [MãCode]</code>")
        return
    code = args[1].upper()
    user_id = message.from_user.id
    user = get_user(user_id, message.from_user.full_name)
    
    if code not in active_codes:
        await message.reply("❌ Mã Giftcode không tồn tại hoặc đã hết hạn!")
        return
        
    gift = active_codes[code]
    if gift["uses"] <= 0:
        del active_codes[code]
        await message.reply("❌ Mã Giftcode đã hết lượt sử dụng!")
        return
        
    user["balance"] += gift["amount"]
    gift["uses"] -= 1
    if gift["uses"] <= 0:
        del active_codes[code]
        
    await message.reply(f"🎁 Nhập code thành công! Bạn nhận được <b>{gift['amount']:,.0f} VND</b> vào tài khoản.")

# --- XỬ LÝ NÚT BẤM MENU NHANH DƯỚI CHAT ---
@dp.message(F.text == "💰 Số Dư")
async def btn_sodu(message: types.Message):
    await cmd_sodu(message)

@dp.message(F.text == "💳 Nạp Tiền")
async def btn_nap(message: types.Message):
    await message.answer("Vui lòng nhập cú pháp nạp tiền: <code>/nap [số tiền]</code>\nVí dụ: <code>/nap 50000</code>")

@dp.message(F.text == "💸 Rút Tiền")
async def btn_rut(message: types.Message):
    await message.answer("Vui lòng nhập cú pháp rút tiền:\n<code>/rut [Số tiền] [Số TK] [Ngân hàng]</code>\nVí dụ: <code>/rut 200000 2105200999999 MB</code>")

@dp.message(F.text == "🎁 Nhập Code")
async def btn_code(message: types.Message):
    await message.answer("Vui lòng nhập cú pháp nhận code:\n<code>/code [MãCode]</code>")

# --- CÁC LỆNH QUẢN TRỊ (ADMIN) ---

@dp.message(Command("cong"))
async def cmd_cong(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        await message.reply("Cú pháp: /cong [số tiền] [id]")
        return
    try:
        amount = float(args[1])
        target_id = int(args[2])
        target_user = get_user(target_id)
        target_user["balance"] += amount
        await message.reply(f"✅ Đã cộng {amount:,.0f} VND cho user {target_id}. Số dư mới: {target_user['balance']:,.0f}")
        try:
            await bot.send_message(target_id, f"🎉 Tài khoản của bạn đã được cộng thêm <b>{amount:,.0f} VND</b> từ hệ thống!")
        except Exception:
            pass
    except Exception as e:
        await message.reply(f"Lỗi: {e}")

@dp.message(Command("tru"))
async def cmd_tru(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 3:
        await message.reply("Cú pháp: /tru [số tiền] [id]")
        return
    try:
        amount = float(args[1])
        target_id = int(args[2])
        target_user = get_user(target_id)
        target_user["balance"] = max(0.0, target_user["balance"] - amount)
        await message.reply(f"✅ Đã trừ {amount:,.0f} VND của user {target_id}. Số dư mới: {target_user['balance']:,.0f}")
    except Exception as e:
        await message.reply(f"Lỗi: {e}")

@dp.message(Command("taocode"))
async def cmd_taocode(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    args = message.text.split()
    if len(args) < 4:
        await message.reply("Cú pháp: /taocode [code] [số tiền] [số lượt]")
        return
    code = args[1].upper()
    try:
        amount = float(args[2])
        uses = int(args[3])
        active_codes[code] = {"amount": amount, "uses": uses}
        await message.reply(f"✅ Đã tạo thành công Giftcode: <code>{code}</code> | Trị giá: <b>{amount:,.0f} VND</b> | Lượt dùng: <b>{uses}</b>")
    except Exception as e:
        await message.reply(f"Lỗi tạo code: {e}")

@dp.message(Command("thongbao"))
async def cmd_thongbao(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    content = message.text.replace("/thongbao", "").strip()
    if not content:
        await message.reply("⚠️ Vui lòng nhập nội dung thông báo.")
        return
    try:
        await bot.send_message(GROUP_CHAT_ID, f"📢 <b>THÔNG BÁO TỪ QUẢN TRỊ VIÊN</b>\n\n{content}")
        await message.reply("✅ Đã gửi thông báo thành công vào nhóm!")
    except Exception as e:
        await message.reply(f"❌ Lỗi gửi thông báo: {e}")

# --- BẮT LỆNH ĐẶT CƯỢC TRONG NHÓM ---
@dp.message()
async def catch_all_messages(message: types.Message):
    if message.chat.id != GROUP_CHAT_ID:
        return
    if not message.text:
        return
        
    text = message.text.lower().strip()
    if text.startswith(("/tai", "/xiu", "/c", "/l", "/chan", "/le")):
        parts = text.split()
        if len(parts) >= 2 and parts[1].isdigit():
            cmd = parts[0].replace("/", "")
            amount = float(parts[1])
            user_id = message.from_user.id
            name = message.from_user.full_name
            user = get_user(user_id, name)
            
            if amount < 1000:
                return
                
            if user["balance"] < amount:
                await message.reply(f"❌ {name}, bạn không đủ tiền cược!")
                return
                
            bet_type = "tai" if cmd == "tai" else ("xiu" if cmd == "xiu" else ("chan" if cmd in ["c", "chan"] else "le"))
            user["balance"] -= amount
            bets_current[user_id] = {"type": bet_type, "amount": amount, "name": name}
            await message.reply(f"✅ <b>{name}</b> cược thành công <b>{amount:,.0f} VND</b> vào cửa <b>{bet_type.upper()}</b>!")

# --- VÒNG LẬP TRÒ CHƠI TỰ ĐỘNG (GAME LOOP) ---
async def game_loop():
    global current_session, current_jackpot, recent_tai_xiu, recent_chan_le, bets_current
    
    await asyncio.sleep(3)
    
    while game_running:
        bets_current.clear()
        
        # 1. BẮT ĐẦU PHIÊN MỚI & MỞ KHÓA CHAT
        await unlock_chat(GROUP_CHAT_ID)
        
        tx_display = " ".join(["🔵" if x == 'T' else "🔴" for x in recent_tai_xiu[-12:]])
        cl_display = " ".join(["⚪" if x == 'C' else "⚫" for x in recent_chan_le[-12:]])
        
        start_text = (
            f"🟢 <b>BẮT ĐẦU PHIÊN MỚI (#{current_session})</b>\n\n"
            f"⏳ <b>Thời gian đặt cược: 40 giây</b>\n"
            f"💰 <b>Hũ Jackpot hiện tại: {current_jackpot:,.0f} VND</b>\n\n"
            f"📊 <b>THỐNG KÊ 12 PHIÊN GẦN NHẤT:</b>\n"
            f"• Tài / Xỉu: {tx_display}\n"
            f"• Chẵn / Lẻ: {cl_display}\n\n"
            f"👇 <i>Gửi lệnh cược ngay vào nhóm:</i>\n"
            f"<code>/Tai 10000</code> | <code>/Xiu 10000</code>\n"
            f"<code>/C 10000</code> (Chẵn) | <code>/L 10000</code> (Lẻ)"
        )
        
        try:
            session_msg = await bot.send_message(GROUP_CHAT_ID, start_text)
        except Exception as e:
            logging.error(f"Lỗi gửi tin nhắn phiên mới: {e}")
            await asyncio.sleep(5)
            continue
            
        # 2. VÒNG LẶP ĐẾM NGƯỢC CẬP NHẬT MỖI 5 GIÂY
        for remaining in range(35, 0, -5):
            await asyncio.sleep(5)
            total_t = sum(b["amount"] for b in bets_current.values() if b["type"] == "tai")
            total_x = sum(b["amount"] for b in bets_current.values() if b["type"] == "xiu")
            
            update_text = (
                f"🟢 <b>PHIÊN MỚI (#{current_session}) - ĐANG NHẬN CƯỢC</b>\n\n"
                f"⏳ Còn lại: <b>{remaining} giây</b>\n"
                f"💰 Tổng cược Tài: <b>{total_t:,.0f} VND</b> | Xỉu: <b>{total_x:,.0f} VND</b>\n"
                f"💎 Hũ Jackpot: <b>{current_jackpot:,.0f} VND</b>\n\n"
                f"👉 Cú pháp: <code>/Tai [tiền]</code> | <code>/Xiu [tiền]</code>"
            )
            try:
                await session_msg.edit_text(update_text)
            except Exception:
                pass
                
        await asyncio.sleep(5)
        
        # 3. KHÓA CHAT & TỔNG KẾT
        await lock_chat(GROUP_CHAT_ID)
        try:
            await session_msg.edit_text(f"🔒 <b>PHIÊN (#{current_session}) ĐÃ ĐÓNG CƯỢC. ĐANG QUAY THƯỞNG...</b>")
        except Exception:
            pass
            
        await asyncio.sleep(1)
        
        # 4. TUNG XÚ XẮC HOẠT ẢNH THẬT
        dice1_obj = await bot.send_dice(GROUP_CHAT_ID, emoji="🎲")
        d1 = dice1_obj.dice.value
        await asyncio.sleep(1)
        
        dice2_obj = await bot.send_dice(GROUP_CHAT_ID, emoji="🎲")
        d2 = dice2_obj.dice.value
        await asyncio.sleep(1)
        
        dice3_obj = await bot.send_dice(GROUP_CHAT_ID, emoji="🎲")
        d3 = dice3_obj.dice.value
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
            b_type = bet["type"]
            b_amt = bet["amount"]
            user = get_user(uid)
            
            won = False
            if b_type == "tai" and is_tai:
                won = True
            elif b_type == "xiu" and not is_tai:
                won = True
            elif b_type == "chan" and total_points % 2 == 0:
                won = True
            elif b_type == "le" and total_points % 2 != 0:
                won = True
                
            if won:
                payout = b_amt * 0.95
                user["balance"] += payout + b_amt
                total_win_money += payout
            else:
                total_lose_money += b_amt
                
        added_jackpot = total_lose_money * 0.01
        current_jackpot += added_jackpot
        
        tx_display_res = " ".join(["🔵" if x == 'T' else "🔴" for x in recent_tai_xiu[-12:]])
        cl_display_res = " ".join(["⚪" if x == 'C' else "⚫" for x in recent_chan_le[-12:]])
        
        result_text = (
            f"🔒 <b>KẾT QUẢ PHIÊN (#{current_session}) - ĐÃ KHÓA CHAT</b>\n\n"
            f"🎲 Xúc xắc: <b>{d1} - {d2} - {d3}</b> ➔ <b>{total_points} điểm</b> ➔ <b>{tx_result} | {cl_result}</b>\n\n"
            f"| 📊 TỔNG ĐIỂM XÚC XẮC: {total_points}\n"
            f"| 💰 TỔNG THẮNG: {total_win_money:,.0f} VND\n"
            f"| 💸 TỔNG THUA: {total_lose_money:,.0f} VND\n"
            f"| 📥 CỘNG HŨ: {added_jackpot:,.0f} VND\n"
            f"| 🏺 HŨ HIỆN TẠI: {current_jackpot:,.0f} VND\n\n"
            f"📊 <b>THỐNG KÊ 12 PHIÊN GẦN NHẤT TÀI XỈU:</b>\n{tx_display_res}\n\n"
            f"📊 <b>CHẴN LẺ:</b>\n{cl_display_res}"
        )
        
        try:
            await bot.send_message(GROUP_CHAT_ID, result_text)
        except Exception as e:
            logging.error(f"Lỗi gửi kết quả phiên: {e}")
            
        current_session += 1
        await asyncio.sleep(5)

# --- KHỞI CHẠY WEB SERVER (GIỮ BOT ONLINE TRÊN RENDER) ---
async def handle_ping(request):
    return web.Response(text="BTV88 Bot is running smoothly!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    logging.info(f"Web server started on port {port}")

async def main():
    await set_bot_commands(bot)
    await start_web_server()
    asyncio.create_task(game_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
