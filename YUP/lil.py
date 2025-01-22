import logging
import asyncio
import os
import asyncpg
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram import F
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext


class SomeStatesGroup(StatesGroup):
    name_state = State()


load_dotenv()

# Получение токена бота из переменной окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")
POSTGRES_HOST = os.getenv("POSTGRES_HOST")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT"))
POSTGRES_DB = os.getenv("POSTGRES_DB")
POSTGRES_USER = os.getenv("POSTGRES_USER")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD")

if not BOT_TOKEN or not POSTGRES_HOST or not POSTGRES_DB or not POSTGRES_USER or not POSTGRES_PASSWORD:
    exit("Error: Missing environment variables for bot or database.")

# Настройка логгирования
logging.basicConfig(level=logging.INFO)

# Создание соединения с базой
async def create_db_pool():
    return await asyncpg.create_pool(
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        database=POSTGRES_DB,
        max_inactive_connection_lifetime=3
    )


# Получение данных о пользователе
async def get_user(pool: asyncpg.Pool, user_id):
    async with pool.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM butterfly WHERE id = $1", user_id)


# Добавление и обновление данных пользователя
async def add_or_update_user(pool: asyncpg.Pool, user: types.User):
    async with pool.acquire() as conn:
        existing_user = await conn.fetchrow("SELECT * FROM butterfly WHERE telegram_id = $1", user.id)
        if existing_user:
            await conn.execute(
                "UPDATE butterfly SET Name = $1 WHERE telegram_id = $2",
                user.first_name, user.id
            )
        else:
            await conn.execute(
                "INSERT INTO butterfly (Name, telegram_id) VALUES ($1, $2)",
                user.first_name, user.id
            )


# Сохранение сообщений
async def save_message(pool: asyncpg.Pool, user_id, text: str):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO messages (user_id, text) VALUES ($1, $2)", user_id, text)


async def save_butterfly_data(pool: asyncpg.Pool, user_id, name: str, state: FSMContext):
    async with pool.acquire() as conn:
        await conn.execute("INSERT INTO butterfly (Name, telegram_id) VALUES ($1, $2)", name, user_id)


# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


# Обработчик команды /start
@dp.message(CommandStart())
async def start_command(message: Message, pool: asyncpg.Pool):
    await add_or_update_user(pool, message.from_user)

    builder = ReplyKeyboardBuilder()
    builder.button(text="Показать инфо")
    builder.button(text="Помощь")
    builder.button(text="Знакомство")
    builder.adjust(2)  # Размещаем кнопки в 2 столбца

    await message.answer(
        "Привет! Я бот Butterfly. Выбери пожалуйста действие:",
        reply_markup=builder.as_markup(resize_keyboard=True),
    )


# Обработчик команды /help
@dp.message(Command("help"))
async def help_command(message: Message, pool: asyncpg.Pool):
    await send_help_message(message, pool)


# Обработчик команды /info
@dp.message(Command("info"))
async def info_command(message: Message, pool: asyncpg.Pool):
    await send_info_message(message, pool)


# Обработчик команды "Знакомство"
@dp.message(Command("Acquaintance"))
async def acquaintance_command(message: Message, pool: asyncpg.Pool, state: FSMContext):
    await send_acquaintance_message(message, pool, state)


# Обработчик callback запросов
@dp.callback_query()
async def handle_callback(callback: CallbackQuery, pool: asyncpg.Pool, state: FSMContext):
    if callback.data == "show_info":
        await send_info_message(callback.message, pool)
        await callback.answer()  # Подтверждаем нажатие на инлайн кнопку
    elif callback.data == "show_help":
        await send_help_message(callback.message, pool)
        await callback.answer()  # Подтверждаем нажатие на инлайн кнопку
    elif callback.data == "show_Acquaintance":
        await send_acquaintance_message(callback.message, pool, state)
        await callback.answer()


# Функция отправки сообщения с информацией
async def send_info_message(message: Message, pool: asyncpg.Pool):
    user = await get_user(pool, message.from_user.id)

    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="Инфо еще раз", callback_data="show_info")
    inline_builder.button(text="Помощь", callback_data="show_help")
    inline_builder.button(text="Знакомство", callback_data="show_Acquaintance")

    user_info = f"Информация о пользователе:\n"
    if user:
        user_info += f"ID: {user['id']}\n"
        user_info += f"Name: {user['name']}\n"
        user_info += f"telegram_id: {user['telegram_id']}\n"
    else:
        user_info = "Пользователь не найден"

    await message.answer(
        f"{user_info}\n\n"
        "Я простой бот, написанный на aiogram!\n"
        "Версия aiogram: 3.17.0\n"
        "Создала меня: Сливкина Марина.",
        disable_web_page_preview=True,
        reply_markup=inline_builder.as_markup()
    )


# Функция отправки сообщения в Знакомство
async def send_acquaintance_message(message: Message, pool: asyncpg.Pool, state: FSMContext):
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="Инфо", callback_data="show_info")
    inline_builder.button(text="Помощь", callback_data="show_help")
    inline_builder.button(text="Знакомство еще раз", callback_data="show_Acquaintance")

    await message.answer(
        "Напишите ваше имя",
        disable_web_page_preview=True,
        reply_markup=inline_builder.as_markup()
    )
    await state.set_state(SomeStatesGroup.name_state)


dp.message.register(send_acquaintance_message, F.text == "Знакомство")


async def send_name(message: Message, pool: asyncpg.Pool, state: FSMContext):
    await save_butterfly_data(pool, message.from_user.id, message.text, state)
    await message.answer(f"Привет - {message.text}!")
    await state.clear()


dp.message.register(send_name, StateFilter(SomeStatesGroup.name_state))


# Функция отправки сообщения помощи
async def send_help_message(message: Message, pool: asyncpg.Pool):
    inline_builder = InlineKeyboardBuilder()
    inline_builder.button(text="Инфо", callback_data="show_info")
    inline_builder.button(text="Помощь еще раз", callback_data="show_help")
    inline_builder.button(text="Знакомство", callback_data="show_Acquaintance")

    await message.answer(
        "Вот мои команды:\n"
        "/start - начать работу\n"
        "/help - показать это сообщение\n"
        "/info - получить информацию о боте и создателе\n"
        "/Acquaintance - бот познакомиться с вами.",
        reply_markup=inline_builder.as_markup()
    )


# Обработчик текстовых сообщений
@dp.message()
async def handle_message(message: Message, pool: asyncpg.Pool):
    await save_message(pool, message.from_user.id, message.text)
    if message.text == "Показать инфо":
        await send_info_message(message, pool)
    elif message.text == "Помощь":
        await send_help_message(message, pool)


# Функция для запуска бота
async def main():
    pool = await create_db_pool()
    try:
        await on_startup(pool)
        await dp.start_polling(bot, pool=pool)
    finally:
        await pool.close()
        await bot.session.close()
        



async def on_startup(pool: asyncpg.Pool):
    logging.info("Бот запущен")

    for handler in dp.message.handlers:
        handler.func = lambda *args, pool=pool, **kwargs: asyncio.run(handler.func(*args, pool=pool, **kwargs))

    for handler in dp.callback_query.handlers:
       handler.func = lambda *args, pool=pool, **kwargs: asyncio.run(handler.func(*args, pool=pool, **kwargs))

if __name__ == "__main__":
    asyncio.run(main())
    


# https://www.psycopg.org/psycopg3/docs/basic/usage.html

# https://chatgptchatapp.com/