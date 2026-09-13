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
TOKEN = os.getenv("BOT_TOKEN", "8954729214:AAF1Bwsm9CGJbBY7AX4C-T8j7ra9q18AMTc")
ADMIN_ID = int(os.getenv("ADMIN_ID", "8985238179"))
GROUP_CHAT_ID = None  # Sẽ tự động cập nhật ID chuẩn ngay khi có tin nhắn trong nhóm

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# --- BIẾN TRẠNG THÁI TRÒ CHƠI ---
current_session = 105027
current_jackpot = 600000.0
recent_tai_xiu = ['T', 'X', 'T', 'X', 'T', 'X', 'T', 'X', 'T', 'X', 'T', 'X']
recent_chan_le = ['C', 'L', 'C', 'L', 'C', 'L', 'C', 'L', 'C', 'L', 'C', 'L']
game_running = True

users_db = {
    ADMIN_ID: {"balance": 50000000.0, "name": "Admin Tổng"}
}
bets_current = {} 
active_codes = {} 

def get_user(user_id: int, name: str = "Thành viên"):
    if user_id not in users_db:
        users_db[user_id] = {"balance": 50000.0, "name": name}
    return users_db[user_id]

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Mở menu chính / Hướng dẫn"),
        BotCommand(command="sodu", description="Kiểm tra số dư ví"),
        BotCommand(command="nap", description="Nạp tiền tự động / QR Code"),
        BotCommand(command="rut", description="Tạo lệnh rút tiền"),
        BotCommand(command="code", description="Nhập Giftcode nhận thưởng"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())

main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💰 Số Dư"), KeyboardButton(text="💳 Nạp Tiền")],
        [KeyboardButton(text="💸 Rút Tiền"), KeyboardButton(text="🎁 Nhập Code")]
    ],
    resize_keyboard=True
)

async def lock_chat(chat_id: int):
    try:
        await bot.set_chat_permissions(
            chat_id=chat_id,
            permissions=ChatPermissions(can_send_messages=False)
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

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    get_user(message.from_user.id, message.from_user.full_name)
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
        f"• Nội dung chuyển khoản: <code>{content_nap}</code>"
    )
    qr_url = f"https://img.vietqr.io/image/MB-2105200999999-compact.png?amount={amount}&addInfo={content_nap}&accountName=KHONG%20QUOC%20BAO"
    try:
        await message.answer_photo(photo=qr_url, caption=qr_caption)
    except Exception:
        await message.answer(qr_caption)

@dp.message(Command("rut"))
async def cmd_rut(message: types.Message):
    args = message.text.split(maxsplit=3)
    user_id = message.from_user.id
    name = message.from_user.full_name
    user = get_user(user_id, name)
    
    if len(args) < 4:
        await message.reply("🏛️ Cú pháp: <code>/rut [Số tiền] [Số TK] [Ngân hàng]</code>")
        return
    try:
        amount = float(args[1])
        stk, bank = args[2], args[3]
    except ValueError:
        await message.reply("❌ Số tiền không hợp lệ.")
        return
        
    if user["balance"] < amount:
        await message.reply(f"❌ Số dư không đủ! Số dư: {user['balance']:,.0f} VND")
        return
        
    user["balance"] -= amount
    await message.reply(f"✅ Đã tạo yêu cầu rút <b>{amount:,.0f} VND</b> về TK <code>{stk} ({bank})</code> thành công!")

@dp.message(Command("code"))
async def cmd_code(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.reply("⚠️ Cú pháp: <code>/code [MãCode]</code>")
        return
    code = args[1].upper()
    user = get_user(message.from_user.id, message.from_user.full_name)
    if code not in active_codes or active_codes[code]["uses"] <= 0:
        await message.reply("❌ Mã Giftcode không tồn tại hoặc đã hết hạn!")
        return
    gift = active_codes[code]
    user["balance"] += gift["amount"]
    gift["uses"] -= 1
    if gift["uses"] <= 0:
        del active_codes[code]
    await message.reply(f"🎁 Bạn nhận được <b>{gift['amount']:,.0f} VND</b>!")

@dp.message(F.text == "💰 Số Dư")
async def btn_sodu(message: types.Message): await cmd_sodu(message)

@dp.message(F.text == "💳 Nạp Tiền")
async def btn_nap(message: types.Message): await message.answer("Cú pháp: <code>/nap [số tiền]</code>")

@dp.message(F.text == "💸 Rút Tiền")
async def btn_rut(message: types.Message): await message.answer("Cú pháp: <code>/rut [Số tiền] [Số TK] [Ngân hàng]</code>")

@dp.message(F.text == "🎁 Nhập Code")
async def btn_code(message: types.Message): await message.answer("Cú pháp: <code>/code [MãCode]</code>")

# --- LÍNH GÁCH TỰ ĐỘNG BẮT ID NHÓM VÀ XỬ LÝ CƯỢC ---
@dp.message()
async def catch_all_messages(message: types.Message):
    global GROUP_CHAT_ID
    # Tự động cập nhật ID nhóm chuẩn khi có bất kỳ tin nhắn nào trong nhóm
    if message.chat.type in ["group", "supergroup"]:
        if GROUP_CHAT_ID != message.chat.id:
            GROUP_CHAT_ID = message.chat.id
            logging.info(f"🎯 Đã tự động cập nhật ID Nhóm chuẩn: {GROUP_CHAT_ID}")
            
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
                
                if amount < 1000: return
                if user["balance"] < amount:
                    await message.reply(f"❌ {name}, tài khoản không đủ tiền cược!")
                    return
                    
                bet_type = "tai" if cmd == "tai" else ("xiu" if cmd == "xiu" else ("chan" if cmd in ["c", "chan"] else "le"))
                user["balance"] -= amount
                bets_current[user_id] = {"type": bet_type, "amount": amount, "name": name}
                await message.reply(f"✅ <b>{name}</b> cược <b>{amount:,.0f} VND</b> vào <b>{bet_type.upper()}</b>!")

# --- VÒNG LẬP TRÒ CHƠI ---
async def game_loop():
    global current_session, current_jackpot, recent_tai_xiu, recent_chan_le, bets_current, GROUP_CHAT_ID
    
    await asyncio.sleep(3)
    logging.info("Game loop started successfully!")
    
    while game_running:
        try:
            # Chờ nhận diện ID nhóm nếu chưa có
            if not GROUP_CHAT_ID:
                logging.info("⏳ Đang chờ tin nhắn trong nhóm để tự động nhận dạng Group ID...")
                await asyncio.sleep(5)
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
                    user["balance"] += payout + b_amt
                    total_win_money += payout
                else:
                    total_lose_money += b_amt
                    
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
            await asyncio.sleep(3)
            
        except Exception as e:
            logging.error(f"Lỗi game loop: {e}")
            await asyncio.sleep(5)

async def handle_ping(request):
    return web.Response(text="BTV88 Bot Running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await set_bot_commands(bot)
    await start_web_server()
    asyncio.create_task(game_loop())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
