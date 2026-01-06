# pip install aiogram aiohttp
import asyncio
import logging
from aiohttp import ClientSession
from aiogram import Bot, Dispatcher, F, Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

API_TOKEN = "00000000000"  # ← твой токен
EXCHANGE_API = "https://api.exchangerate-api.com/v4/latest/"

# Исправленная инициализация бота с хранилищем
storage = MemoryStorage()
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=storage)

# Состояния для FSM
class ConvertStates(StatesGroup):
    waiting_for_amount = State()

# Популярные валюты (можно расширить)
CURRENCIES = {
    "USD": "🇺🇸 USD", "EUR": "🇪🇺 EUR", "RUB": "🇷🇺 RUB",
    "GBP": "🇬🇧 GBP", "CNY": "🇨🇳 CNY", "KZT": "🇰🇿 KZT",
    "BYN": "🇧🇾 BYN", "UAH": "🇺🇦 UAH", "PLN": "🇵🇱 PLN"
}

async def get_rates(base: str) -> dict:
    try:
        async with ClientSession() as session:
            async with session.get(f"{EXCHANGE_API}{base}") as resp:
                if resp.status != 200:
                    # Если основное API не работает, пробуем альтернативное
                    return await get_rates_fallback(base)
                
                data = await resp.json()
                
                # Проверяем наличие rates в ответе
                if "rates" not in data:
                    return await get_rates_fallback(base)
                    
                return data["rates"]
    except Exception as e:
        logging.error(f"Error getting rates for {base}: {e}")
        return await get_rates_fallback(base)

async def get_rates_fallback(base: str) -> dict:
    """Альтернативный API на случай ошибки"""
    try:
        async with ClientSession() as session:
            # Используем другой API с поддержкой большего количества валют
            url = f"https://api.exchangerate.host/latest?base={base}"
            async with session.get(url) as resp:
                data = await resp.json()
                
                if data.get("success", False) and "rates" in data:
                    return data["rates"]
                else:
                    # Если оба API не работают, возвращаем пустые курсы
                    logging.error("Both APIs failed")
                    return {}
    except Exception as e:
        logging.error(f"Fallback API also failed: {e}")
        return {}

@dp.message(CommandStart())
async def start(msg: Message):
    kb = [[InlineKeyboardButton(text=v, callback_data=f"from_{k}")]
          for k, v in CURRENCIES.items()]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await msg.answer(
        "🔄 Выбери валюту <b>из которой</b> конвертировать:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("from_"))
async def choose_from(cb: CallbackQuery):
    from_curr = cb.data.split("_")[1]
    kb = [[InlineKeyboardButton(text=v, callback_data=f"to_{from_curr}_{k}")]
          for k, v in CURRENCIES.items() if k != from_curr]
    keyboard = InlineKeyboardMarkup(inline_keyboard=kb)
    await cb.message.edit_text(
        f"✅ Из: <b>{CURRENCIES[from_curr]}</b>\n"
        "Теперь выбери валюту <b>в которую</b> конвертировать:",
        reply_markup=keyboard
    )

@dp.callback_query(F.data.startswith("to_"))
async def choose_to(cb: CallbackQuery, state: FSMContext):
    _, from_curr, to_curr = cb.data.split("_")
    
    # Сохраняем данные в состоянии
    await state.update_data(from_curr=from_curr, to_curr=to_curr)
    
    await cb.message.edit_text(
        f"🔄 Готово!\n"
        f"<b>{CURRENCIES[from_curr]}</b> → <b>{CURRENCIES[to_curr]}</b>\n\n"
        f"Введи сумму в {CURRENCIES[from_curr]}:",
    )
    
    # Устанавливаем состояние ожидания суммы
    await state.set_state(ConvertStates.waiting_for_amount)

@dp.message(ConvertStates.waiting_for_amount, F.text.regexp(r"^\d+(\.\d+)?$"))
async def convert(msg: Message, state: FSMContext):
    # Получаем сохраненные данные
    user_data = await state.get_data()
    from_curr = user_data.get("from_curr")
    to_curr = user_data.get("to_curr")
    
    if not from_curr or not to_curr:
        await msg.answer("Сначала выбери направление через /start")
        await state.clear()
        return

    amount = float(msg.text)
    
    # Показываем сообщение о загрузке
    loading_msg = await msg.answer("⏳ Получаем актуальные курсы...")
    
    rates = await get_rates(from_curr)
    
    # Удаляем сообщение о загрузке
    await loading_msg.delete()

    if not rates or to_curr not in rates:
        await msg.answer(
            f"❌ Не удалось получить курс для {CURRENCIES[from_curr]} → {CURRENCIES[to_curr]}\n"
            f"Попробуйте другую валютную пару или повторите позже.\n\n"
            "Снова конвертировать — /start"
        )
        await state.clear()
        return

    result = amount * rates[to_curr]

    await msg.answer(
        f"<b>{amount:,.2f} {CURRENCIES[from_curr]}</b> = "
        f"<b>{result:,.2f} {CURRENCIES[to_curr]}</b>\n"
        f"Курс: 1 {from_curr} = {rates[to_curr]:.4f} {to_curr}\n\n"
        "Снова конвертировать — /start",
        reply_markup=None
    )
    
    # Очищаем состояние
    await state.clear()

@dp.message(ConvertStates.waiting_for_amount)
async def process_invalid_amount(msg: Message):
    await msg.answer("Пожалуйста, введите корректную сумму (только числа):")

@dp.message()
async def other_messages(msg: Message):
    await msg.answer("Для начала конвертации валют используйте команду /start")

async def main():
    logging.basicConfig(level=logging.INFO)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
