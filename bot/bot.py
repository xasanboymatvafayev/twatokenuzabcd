import asyncio
import logging
import random
from datetime import datetime
import pytz
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import aiohttp
import os

BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN")
API_BASE = os.getenv("API_BASE", "http://localhost:8000/api")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-casino-domain.com")
SECRET = os.getenv("SECRET_KEY", "your-super-secret-key-c")[:20]

# Admin karta raqamlari (vergul bilan ajratilgan)
ADMIN_CARDS = os.getenv("ADMIN_CARDS", "8600000000000000").split(",")

UZBEKISTAN_TZ = pytz.timezone("Asia/Tashkent")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ============= FSM STATES =============
class DepositStates(StatesGroup):
    waiting_amount = State()
    waiting_confirm = State()

class WithdrawStates(StatesGroup):
    waiting_amount = State()
    waiting_card = State()
    waiting_confirm = State()

class PasswordStates(StatesGroup):
    waiting_new_password = State()

# ============= HELPERS =============
def uz_time():
    return datetime.now(UZBEKISTAN_TZ).strftime("%Y-%m-%d %H:%M:%S")

def get_admin_card():
    return random.choice(ADMIN_CARDS).strip()

def get_admin_ids():
    return [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]

async def api_post(endpoint: str, data: dict):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{API_BASE}{endpoint}",
                json=data,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return await resp.json(), resp.status
    except Exception as e:
        logging.error(f"API error {endpoint}: {e}")
        return {}, 500

async def api_register(telegram_id: str):
    data, status = await api_post("/auth/telegram-register", {"telegram_id": telegram_id, "secret": SECRET})
    return data

# ============= KEYBOARDS =============
def main_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎮 O'yin O'ynash", web_app=WebAppInfo(url=WEBAPP_URL))],
        [
            InlineKeyboardButton(text="👤 Profil", callback_data="profile"),
            InlineKeyboardButton(text="💰 Balans", callback_data="balance")
        ],
        [
            InlineKeyboardButton(text="➕ To'ldirish", callback_data="deposit"),
            InlineKeyboardButton(text="➖ Yechish", callback_data="withdraw")
        ],
        [InlineKeyboardButton(text="🎟 Promokod", callback_data="promo")]
    ])

def cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")]
    ])

def confirm_deposit_keyboard(amount: int, real_amount: int, card: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text=f"✅ {real_amount:,} so'm o'tkazdim",
            callback_data=f"deposit_done:{amount}:{real_amount}:{card}"
        )],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")]
    ])

# ============= START =============
@dp.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    user_id = str(message.from_user.id)
    result = await api_register(user_id)

    if not result:
        await message.answer("❌ Server bilan bog'lanishda xatolik. Qayta urinib ko'ring.")
        return

    if result.get("exists"):
        await message.answer(
            f"👋 *Xush kelibsiz qaytib!*\n\n"
            f"👤 Login: `{result.get('username', user_id)}`\n"
            f"💰 Balans: *{result.get('balance', 0):,}* so'm\n\n"
            f"O'yin o'ynash uchun quyidagi tugmani bosing:",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    else:
        username = result.get('username', user_id)
        password = result.get('password', '-')
        await message.answer(
            f"🎰 *Casino'ga xush kelibsiz!*\n\n"
            f"✅ Hisobingiz yaratildi!\n\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"👤 Login: `{username}`\n"
            f"🔐 Parol: `{password}`\n"
            f"━━━━━━━━━━━━━━━━\n\n"
            f"⚠️ Bu malumotlarni saqlang!\n"
            f"Web Appga kirish uchun ishlatiladi.\n\n"
            f"Balans toldirish uchun /deposit yozing.",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )

# ============= CANCEL =============
@dp.callback_query(F.data == "cancel")
async def cancel_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Bekor qilindi.", reply_markup=None)
    await callback.message.answer("Asosiy menyu:", reply_markup=main_keyboard())
    await callback.answer()

# ============= PROFILE =============
@dp.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    result = await api_register(user_id)

    if not result:
        await callback.answer("❌ Server xatoligi!", show_alert=True)
        return

    text = (
        f"👤 *Profilingiz*\n\n"
        f"🆔 Login: `{result.get('username', user_id)}`\n"
        f"💰 Balans: *{result.get('balance', 0):,}* so'm\n"
        f"📅 Ro'yxatdan o'tgan: {result.get('created_at', '-')[:10] if result.get('created_at') else '-'}"
    )

    try:
        await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=main_keyboard())
    except Exception:
        await callback.message.answer(text, parse_mode="Markdown", reply_markup=main_keyboard())
    await callback.answer()

# ============= BALANCE =============
@dp.callback_query(F.data == "balance")
async def balance_callback(callback: types.CallbackQuery):
    user_id = str(callback.from_user.id)
    result = await api_register(user_id)
    balance = result.get('balance', 0) if result else 0
    await callback.answer(f"💰 Balansingiz: {balance:,} so'm", show_alert=True)

# ============= DEPOSIT =============
@dp.callback_query(F.data == "deposit")
async def deposit_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(DepositStates.waiting_amount)
    await callback.message.answer(
        "💳 *Balans to'ldirish*\n\n"
        "Qancha so'm kiritmoqchisiz?\n"
        "*(Minimum: 10,000 so'm)*\n\n"
        "Faqat raqam yozing, masalan: `50000`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()

@dp.message(Command("deposit"))
async def cmd_deposit(message: types.Message, state: FSMContext):
    await state.set_state(DepositStates.waiting_amount)
    await message.answer(
        "💳 *Balans to'ldirish*\n\n"
        "Qancha so'm kiritmoqchisiz?\n"
        "*(Minimum: 10,000 so'm)*\n\n"
        "Faqat raqam yozing, masalan: `50000`",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )

@dp.message(DepositStates.waiting_amount)
async def deposit_amount_received(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip().replace(",", "").replace(" ", ""))
        if amount < 10000:
            await message.answer("❌ Minimum 10,000 so'm kiritishingiz kerak!", reply_markup=cancel_keyboard())
            return
    except Exception:
        await message.answer("❌ Faqat raqam kiriting!", reply_markup=cancel_keyboard())
        return

    # Random qo'shimcha summa (100-500 so'm)
    extra = random.randint(100, 500)
    real_amount = amount + extra
    card = get_admin_card()

    await state.update_data(amount=amount, real_amount=real_amount, card=card)

    await message.answer(
        f"💳 *To'lov ma'lumotlari*\n\n"
        f"💵 Siz kiritmoqchi bo'lgan: *{amount:,}* so'm\n"
        f"💰 O'tkazish kerak bo'lgan summa: *{real_amount:,}* so'm\n\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"🏦 Karta raqami:\n"
        f"`{card}`\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"⚠️ *Aynan {real_amount:,} so'm o'tkazing!*\n"
        f"O'tkazgandan so'ng pastdagi tugmani bosing.",
        parse_mode="Markdown",
        reply_markup=confirm_deposit_keyboard(amount, real_amount, card)
    )
    await state.set_state(DepositStates.waiting_confirm)

@dp.callback_query(F.data.startswith("deposit_done:"))
async def deposit_done_callback(callback: types.CallbackQuery, state: FSMContext):
    parts = callback.data.split(":")
    amount = int(parts[1])
    real_amount = int(parts[2])
    card = parts[3]

    user_id = str(callback.from_user.id)
    username = callback.from_user.username or f"id{user_id}"
    time_now = uz_time()

    # Adminga xabar yuborish
    for admin_id in get_admin_ids():
        try:
            admin_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_approve:{user_id}:{amount}"),
                    InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_reject:{user_id}:{amount}")
                ]
            ])
            await bot.send_message(
                admin_id,
                f"💰 *YANGI TO'LDIRISH SO'ROVI*\n\n"
                f"👤 @{username}\n"
                f"🆔 Telegram ID: `{user_id}`\n"
                f"💵 Talab qilingan: *{amount:,}* so'm\n"
                f"💰 O'tkazilgan: *{real_amount:,}* so'm\n"
                f"🏦 Karta: `{card}`\n"
                f"⏰ Vaqt: `{time_now}`",
                parse_mode="Markdown",
                reply_markup=admin_kb
            )
        except Exception as e:
            logging.error(f"Admin xabari yuborilmadi {admin_id}: {e}")

    await state.clear()
    await callback.message.edit_text(
        f"✅ *So'rovingiz yuborildi!*\n\n"
        f"💵 Summa: *{amount:,}* so'm\n"
        f"⏰ Vaqt: `{time_now}`\n\n"
        f"Admin tasdiqlashini kuting...",
        parse_mode="Markdown"
    )
    await callback.answer()

# ============= ADMIN TASDIQLASH =============
@dp.callback_query(F.data.startswith("adm_approve:"))
async def admin_approve(callback: types.CallbackQuery):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    parts = callback.data.split(":")
    user_telegram_id = parts[1]
    amount = int(parts[2])

    # Backend orqali balans qo'shish
    data, status = await api_post("/payments/admin/add-balance", {
        "telegram_id": user_telegram_id,
        "amount": amount,
        "secret": SECRET
    })

    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ *TASDIQLANDI* - {uz_time()}",
        parse_mode="Markdown"
    )

    try:
        await bot.send_message(
            int(user_telegram_id),
            f"✅ *To'lovingiz tasdiqlandi!*\n\n"
            f"💰 *{amount:,}* so'm balansingizga qo'shildi.\n"
            f"⏰ Vaqt: `{uz_time()}`",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    except Exception:
        pass
    await callback.answer("✅ Tasdiqlandi!")

@dp.callback_query(F.data.startswith("adm_reject:"))
async def admin_reject(callback: types.CallbackQuery):
    admin_ids = get_admin_ids()
    if callback.from_user.id not in admin_ids:
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return

    parts = callback.data.split(":")
    user_telegram_id = parts[1]
    amount = int(parts[2])

    await callback.message.edit_text(
        callback.message.text + f"\n\n❌ *RAD ETILDI* - {uz_time()}",
        parse_mode="Markdown"
    )

    try:
        await bot.send_message(
            int(user_telegram_id),
            f"❌ *To'lovingiz rad etildi!*\n\n"
            f"💵 Summa: *{amount:,}* so'm\n"
            f"⏰ Vaqt: `{uz_time()}`\n\n"
            f"Muammo bo'lsa admin bilan bog'laning.",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await callback.answer("❌ Rad etildi!")

# ============= WITHDRAW =============
@dp.callback_query(F.data == "withdraw")
async def withdraw_callback(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(WithdrawStates.waiting_amount)
    await callback.message.answer(
        "💸 *Balans yechish*\n\n"
        "Qancha so'm yechmoqchisiz?\n"
        "*(Minimum: 10,000 so'm)*\n\n"
        "Faqat raqam yozing:",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )
    await callback.answer()

@dp.message(WithdrawStates.waiting_amount)
async def withdraw_amount_received(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text.strip().replace(",", "").replace(" ", ""))
        if amount < 10000:
            await message.answer("❌ Minimum 10,000 so'm!", reply_markup=cancel_keyboard())
            return
    except Exception:
        await message.answer("❌ Faqat raqam kiriting!", reply_markup=cancel_keyboard())
        return

    await state.update_data(amount=amount)
    await state.set_state(WithdrawStates.waiting_card)
    await message.answer(
        f"💳 Yechish summasi: *{amount:,}* so'm\n\n"
        f"Karta raqamingizni kiriting:\n"
        f"_(8600... yoki 9860...)_",
        parse_mode="Markdown",
        reply_markup=cancel_keyboard()
    )

@dp.message(WithdrawStates.waiting_card)
async def withdraw_card_received(message: types.Message, state: FSMContext):
    card = message.text.strip().replace(" ", "")
    if len(card) < 16 or not card.isdigit():
        await message.answer("❌ To'g'ri karta raqamini kiriting (16 raqam)!", reply_markup=cancel_keyboard())
        return

    data = await state.get_data()
    amount = data['amount']
    await state.update_data(card=card)
    await state.set_state(WithdrawStates.waiting_confirm)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="withdraw_confirm")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel")]
    ])

    await message.answer(
        f"💸 *Yechish ma'lumotlari*\n\n"
        f"💵 Summa: *{amount:,}* so'm\n"
        f"💳 Karta: `{card}`\n\n"
        f"Tasdiqlaysizmi?",
        parse_mode="Markdown",
        reply_markup=kb
    )

@dp.callback_query(F.data == "withdraw_confirm")
async def withdraw_confirm_callback(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    amount = data.get('amount', 0)
    card = data.get('card', '-')
    user_id = str(callback.from_user.id)
    username = callback.from_user.username or f"id{user_id}"
    time_now = uz_time()

    for admin_id in get_admin_ids():
        try:
            admin_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ To'landi", callback_data=f"adm_withdraw_ok:{user_id}:{amount}"),
                    InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_withdraw_rej:{user_id}:{amount}")
                ]
            ])
            await bot.send_message(
                admin_id,
                f"💸 *YANGI YECHISH SO'ROVI*\n\n"
                f"👤 @{username}\n"
                f"🆔 ID: `{user_id}`\n"
                f"💵 Summa: *{amount:,}* so'm\n"
                f"💳 Karta: `{card}`\n"
                f"⏰ Vaqt: `{time_now}`",
                parse_mode="Markdown",
                reply_markup=admin_kb
            )
        except Exception as e:
            logging.error(f"Admin xabari yuborilmadi: {e}")

    await state.clear()
    await callback.message.edit_text(
        f"✅ *Yechish so'rovi yuborildi!*\n\n"
        f"💵 Summa: *{amount:,}* so'm\n"
        f"💳 Karta: `{card}`\n"
        f"⏰ Vaqt: `{time_now}`\n\n"
        f"Admin tasdiqlashini kuting...",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("adm_withdraw_ok:"))
async def admin_withdraw_ok(callback: types.CallbackQuery):
    if callback.from_user.id not in get_admin_ids():
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    parts = callback.data.split(":")
    user_telegram_id = parts[1]
    amount = int(parts[2])

    await callback.message.edit_text(
        callback.message.text + f"\n\n✅ *TO'LANDI* - {uz_time()}",
        parse_mode="Markdown"
    )
    try:
        await bot.send_message(
            int(user_telegram_id),
            f"✅ *Yechish amalga oshirildi!*\n\n"
            f"💰 *{amount:,}* so'm kartangizga o'tkazildi.\n"
            f"⏰ Vaqt: `{uz_time()}`",
            parse_mode="Markdown",
            reply_markup=main_keyboard()
        )
    except Exception:
        pass
    await callback.answer("✅ Bajarildi!")

@dp.callback_query(F.data.startswith("adm_withdraw_rej:"))
async def admin_withdraw_rej(callback: types.CallbackQuery):
    if callback.from_user.id not in get_admin_ids():
        await callback.answer("❌ Ruxsat yo'q!", show_alert=True)
        return
    parts = callback.data.split(":")
    user_telegram_id = parts[1]
    amount = int(parts[2])

    await callback.message.edit_text(
        callback.message.text + f"\n\n❌ *RAD ETILDI* - {uz_time()}",
        parse_mode="Markdown"
    )
    try:
        await bot.send_message(
            int(user_telegram_id),
            f"❌ *Yechish rad etildi!*\n\n"
            f"💵 Summa: *{amount:,}* so'm\n"
            f"Muammo bo'lsa admin bilan bog'laning.",
            parse_mode="Markdown"
        )
    except Exception:
        pass
    await callback.answer("❌ Rad etildi!")

# ============= PROMO =============
@dp.callback_query(F.data == "promo")
async def promo_callback(callback: types.CallbackQuery):
    await callback.message.answer(
        "🎟 *Promokod kiritish*\n\n"
        "Quyidagi formatda yozing:\n"
        "`/promo KODINGIZ`",
        parse_mode="Markdown"
    )
    await callback.answer()

@dp.message(Command("promo"))
async def cmd_promo(message: types.Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❌ Format: `/promo KODINGIZ`", parse_mode="Markdown")
        return
    code = parts[1].upper()
    user_id = str(message.from_user.id)
    result = await api_register(user_id)
    username = result.get('username', user_id)

    # Apply promo via API
    data, status = await api_post("/promocodes/apply", {
        "code": code,
        "deposit_amount": 0
    })
    # Note: needs token, redirect to webapp
    await message.answer(
        f"🎟 Promokod faollashtirish uchun Web Appga kiring:\n{WEBAPP_URL}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎮 Web App", web_app=WebAppInfo(url=WEBAPP_URL))]
        ])
    )

# ============= ADMIN =============
@dp.message(Command("admin"))
async def cmd_admin(message: types.Message):
    if message.from_user.id not in get_admin_ids():
        await message.answer("❌ Ruxsat yo'q!")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Admin Panel", web_app=WebAppInfo(url=f"{WEBAPP_URL.rstrip('/')}/admin"))],
    ])
    await message.answer("👨‍💼 *Admin Panel*", parse_mode="Markdown", reply_markup=kb)

# ============= RUN =============
async def main():
    logging.info("Bot ishga tushmoqda...")
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(main())
