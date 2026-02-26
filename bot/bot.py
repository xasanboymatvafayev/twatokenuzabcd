import asyncio
import logging
import os
import random
import aiohttp
import pytz
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
API_BASE  = os.getenv("API_BASE", "https://twatokenuzabcd-production-f493.up.railway.app/api")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://twatokenuzabcd.vercel.app")
SECRET    = os.getenv("SECRET", os.getenv("SECRET_KEY", ""))[:20]
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
ADMIN_CARDS = os.getenv("ADMIN_CARDS", "").split(",")
UZ_TZ = pytz.timezone("Asia/Tashkent")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

def uz_time():
    return datetime.now(UZ_TZ).strftime("%Y-%m-%d %H:%M:%S")

def fmt(n):
    return f"{int(n):,}".replace(",", " ")

# ===== FSM =====
class DepositStates(StatesGroup):
    waiting_amount = State()
    waiting_confirm = State()

class WithdrawStates(StatesGroup):
    waiting_amount = State()
    waiting_card = State()

class PasswordStates(StatesGroup):
    waiting_confirm = State()

# ===== KLAVIATURA =====
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🎮 O'yin O'ynash", web_app=WebAppInfo(url=WEBAPP_URL))],
        [KeyboardButton(text="👤 Profil"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="➕ To'ldirish"), KeyboardButton(text="➖ Yechish")],
        [KeyboardButton(text="🎟 Promokod")],
    ], resize_keyboard=True)

# ===== API HELPER =====
async def api_post(endpoint, data):
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{API_BASE}{endpoint}", json=data, timeout=aiohttp.ClientTimeout(total=10)) as r:
                status = r.status
                resp = await r.json()
                return status, resp
    except Exception as e:
        logging.error(f"API error {endpoint}: {e}")
        return 0, {}

async def api_get_balance(telegram_id):
    status, data = await api_post("/auth/telegram-register", {"telegram_id": telegram_id, "secret": SECRET})
    if status == 200:
        return data.get("balance", 0)
    return 0

# ===== START =====
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    uid = str(message.from_user.id)

    status, data = await api_post("/auth/telegram-register", {"telegram_id": uid, "secret": SECRET})

    if status != 200:
        await message.answer("❌ Server xatosi. Qayta urinib ko'ring.")
        return

    if data.get("exists"):
        # Eski user
        await message.answer(
            f"👋 Xush kelibsiz qaytib!\n\n"
            f"👤 Login: `{data.get('username', uid)}`\n"
            f"💰 Balans: *{fmt(data.get('balance', 0))}* so'm\n\n"
            f"Parolni unutdingizmi? /parol buyrug'ini yuboring.",
            parse_mode="Markdown",
            reply_markup=main_kb()
        )
    else:
        # Yangi user
        await message.answer(
            f"🎰 *Casino'ga xush kelibsiz!*\n\n"
            f"✅ Hisobingiz yaratildi!\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 Login: `{data.get('username', uid)}`\n"
            f"🔑 Parol: `{data.get('password', '')}`\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ Bu parolni saqlang!\n"
            f"Web Appga kirish uchun ishlatiladi.",
            parse_mode="Markdown",
            reply_markup=main_kb()
        )

# ===== PAROL RESET =====
@dp.message(Command("parol"))
async def cmd_parol(message: types.Message):
    uid = str(message.from_user.id)
    status, data = await api_post("/auth/reset-password", {"telegram_id": uid, "secret": SECRET})
    if status == 200:
        await message.answer(
            f"🔑 *Yangi parolingiz:*\n\n"
            f"👤 Login: `{data.get('username', uid)}`\n"
            f"🔑 Parol: `{data.get('password', '')}`\n\n"
            f"⚠️ Bu parolni saqlang!",
            parse_mode="Markdown"
        )
    else:
        await message.answer("❌ Xatolik yuz berdi.")

# ===== PROFIL =====
@dp.message(F.text == "👤 Profil")
async def cmd_profil(message: types.Message):
    uid = str(message.from_user.id)
    status, data = await api_post("/auth/telegram-register", {"telegram_id": uid, "secret": SECRET})
    if status == 200:
        await message.answer(
            f"👤 *Profil*\n\n"
            f"🆔 Telegram ID: `{uid}`\n"
            f"👤 Login: `{data.get('username', uid)}`\n"
            f"💰 Balans: *{fmt(data.get('balance', 0))}* so'm\n\n"
            f"Parolni yangilash: /parol",
            parse_mode="Markdown"
        )

# ===== BALANS =====
@dp.message(F.text == "💰 Balans")
async def cmd_balans(message: types.Message):
    uid = str(message.from_user.id)
    balance = await api_get_balance(uid)
    await message.answer(f"💰 Balansingiz: *{fmt(balance)}* so'm", parse_mode="Markdown")

# ===== TO'LDIRISH =====
@dp.message(F.text == "➕ To'ldirish")
async def cmd_deposit(message: types.Message, state: FSMContext):
    await state.set_state(DepositStates.waiting_amount)
    await message.answer(
        "💳 *To'ldirish*\n\nQancha so'm to'ldirmoqchisiz?\n(Minimum: 10,000 so'm)",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="❌ Bekor qilish")]
        ], resize_keyboard=True)
    )

@dp.message(DepositStates.waiting_amount)
async def deposit_amount(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_kb())
        return

    try:
        amount = int(message.text.replace(" ", "").replace(",", ""))
    except:
        await message.answer("❌ Faqat son kiriting!")
        return

    if amount < 10000:
        await message.answer("❌ Minimum 10,000 so'm!")
        return

    extra = random.randint(100, 999)
    total = amount + extra
    card = random.choice(ADMIN_CARDS) if ADMIN_CARDS and ADMIN_CARDS[0] else "8600000000000000"

    await state.update_data(amount=amount, total=total, card=card)
    await state.set_state(DepositStates.waiting_confirm)

    await message.answer(
        f"💳 *To'lov ma'lumotlari:*\n\n"
        f"💳 Karta: `{card}`\n"
        f"💵 O'tkazish summasi: *{fmt(total)}* so'm\n\n"
        f"⚠️ Aynan shu summani o'tkazing!\n"
        f"(+{extra} so'm — tasdiqlash uchun)",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text=f"✅ {fmt(total)} so'm o'tkazdim")],
            [KeyboardButton(text="❌ Bekor qilish")]
        ], resize_keyboard=True)
    )

@dp.message(DepositStates.waiting_confirm)
async def deposit_confirm(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_kb())
        return

    data = await state.get_data()
    amount = data.get("amount")
    total = data.get("total")
    card = data.get("card")
    uid = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name or uid

    # Admin ga xabar
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💰 *Yangi depozit so'rovi*\n\n"
                f"👤 {username} | `{uid}`\n"
                f"💵 So'ragan: {fmt(amount)} so'm\n"
                f"💳 O'tkazgan: *{fmt(total)}* so'm\n"
                f"🏦 Karta: `{card}`\n"
                f"🕐 {uz_time()}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"dep_ok:{uid}:{amount}"),
                    InlineKeyboardButton(text="❌ Rad etish", callback_data=f"dep_no:{uid}:{amount}")
                ]])
            )
        except Exception as e:
            logging.error(f"Admin xabar xatosi: {e}")

    await state.clear()
    await message.answer(
        "✅ So'rovingiz yuborildi!\n\nAdmin tekshirib, balansingizni to'ldiradi.",
        reply_markup=main_kb()
    )

# ===== YECHISH =====
@dp.message(F.text == "➖ Yechish")
async def cmd_withdraw(message: types.Message, state: FSMContext):
    await state.set_state(WithdrawStates.waiting_amount)
    await message.answer(
        "💸 *Yechish*\n\nQancha so'm yechmoqchisiz?\n(Minimum: 10,000 so'm)",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="❌ Bekor qilish")]
        ], resize_keyboard=True)
    )

@dp.message(WithdrawStates.waiting_amount)
async def withdraw_amount(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_kb())
        return
    try:
        amount = int(message.text.replace(" ", "").replace(",", ""))
    except:
        await message.answer("❌ Faqat son kiriting!")
        return
    if amount < 10000:
        await message.answer("❌ Minimum 10,000 so'm!")
        return
    await state.update_data(amount=amount)
    await state.set_state(WithdrawStates.waiting_card)
    await message.answer("💳 Karta raqamingizni kiriting (16 raqam):")

@dp.message(WithdrawStates.waiting_card)
async def withdraw_card(message: types.Message, state: FSMContext):
    if message.text == "❌ Bekor qilish":
        await state.clear()
        await message.answer("Bekor qilindi.", reply_markup=main_kb())
        return

    card = message.text.replace(" ", "")
    if not card.isdigit() or len(card) != 16:
        await message.answer("❌ 16 raqamli karta raqami kiriting!")
        return

    data = await state.get_data()
    amount = data.get("amount")
    uid = str(message.from_user.id)
    username = message.from_user.username or message.from_user.first_name or uid

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"💸 *Yechish so'rovi*\n\n"
                f"👤 {username} | `{uid}`\n"
                f"💵 Summa: *{fmt(amount)}* so'm\n"
                f"💳 Karta: `{card}`\n"
                f"🕐 {uz_time()}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="✅ To'landi", callback_data=f"with_ok:{uid}:{amount}"),
                    InlineKeyboardButton(text="❌ Rad etish", callback_data=f"with_no:{uid}:{amount}")
                ]])
            )
        except Exception as e:
            logging.error(f"Admin xabar xatosi: {e}")

    await state.clear()
    await message.answer(
        "✅ Yechish so'rovi yuborildi!\n\nAdmin ko'rib chiqadi.",
        reply_markup=main_kb()
    )

# ===== PROMOKOD =====
@dp.message(F.text == "🎟 Promokod")
async def cmd_promokod(message: types.Message):
    await message.answer(
        f"🎟 Promokod kiritish uchun Web Appga kiring:\n{WEBAPP_URL}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🎮 Web App", web_app=WebAppInfo(url=WEBAPP_URL))
        ]])
    )

# ===== ADMIN CALLBACK =====
@dp.callback_query(F.data.startswith("dep_ok:"))
async def dep_ok(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    _, uid, amount = callback.data.split(":")
    amount = int(amount)

    status, data = await api_post("/payments/admin/add-balance", {
        "telegram_id": uid, "amount": amount, "secret": SECRET
    })

    if status == 200:
        new_balance = data.get("balance", 0)
        await callback.message.edit_text(
            callback.message.text + f"\n\n✅ *TASDIQLANDI* | Yangi balans: {fmt(new_balance)} so'm",
            parse_mode="Markdown"
        )
        try:
            await bot.send_message(uid, f"✅ Balansingiz *{fmt(amount)}* so'mga to'ldirildi!\n💰 Balans: *{fmt(new_balance)}* so'm", parse_mode="Markdown")
        except: pass
    else:
        await callback.answer("❌ Xatolik!")

@dp.callback_query(F.data.startswith("dep_no:"))
async def dep_no(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    _, uid, amount = callback.data.split(":")
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ *RAD ETILDI*",
        parse_mode="Markdown"
    )
    try:
        await bot.send_message(uid, f"❌ Depozit so'rovingiz rad etildi.\nSabab uchun adminga murojaat qiling.")
    except: pass

@dp.callback_query(F.data.startswith("with_ok:"))
async def with_ok(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    _, uid, amount = callback.data.split(":")
    await callback.message.edit_text(
        callback.message.text + "\n\n✅ *TO'LANDI*",
        parse_mode="Markdown"
    )
    try:
        await bot.send_message(uid, f"✅ *{fmt(int(amount))}* so'm kartangizga o'tkazildi!", parse_mode="Markdown")
    except: pass

@dp.callback_query(F.data.startswith("with_no:"))
async def with_no(callback: types.CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        return
    _, uid, amount = callback.data.split(":")
    await callback.message.edit_text(
        callback.message.text + "\n\n❌ *RAD ETILDI*",
        parse_mode="Markdown"
    )
    try:
        await bot.send_message(uid, "❌ Yechish so'rovingiz rad etildi.")
    except: pass

# ===== MAIN =====
async def main():
    logging.info("Bot ishga tushmoqda...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
