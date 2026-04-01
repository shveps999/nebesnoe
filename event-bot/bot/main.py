import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from bot.config import BOT_TOKEN, ADMIN_ID, MODERATION_CHAT_ID
from bot.database import init_db
from bot.handlers import start, profile, admin
from bot.keyboards import get_main_menu_reply

# Создание папки для логов
os.makedirs("logs", exist_ok=True)

# Отключаем буферизацию
os.environ["PYTHONUNBUFFERED"] = "1"

# Настройка логирования
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

file_handler = logging.FileHandler("logs/bot.log", encoding="utf-8", mode="a")
file_handler.setFormatter(formatter)
file_handler.setLevel(logging.INFO)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
console_handler.setLevel(logging.INFO)

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.handlers = []
root_logger.addHandler(file_handler)
root_logger.addHandler(console_handler)

aiogram_logger = logging.getLogger("aiogram")
aiogram_logger.setLevel(logging.INFO)
aiogram_logger.handlers = []
aiogram_logger.addHandler(file_handler)
aiogram_logger.addHandler(console_handler)

root_logger.info("=== БОТ ЗАПУЩЕН ===")
print(">>> TEST STDOUT MESSAGE <<<", flush=True)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Инициализация БД
    await init_db()
    root_logger.info("База данных инициализирована")
    
    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)
    
    # Middleware для логирования (ПРАВИЛЬНЫЙ СИНТАКСИС ДЛЯ AIОGRAM 3!)
    @dp.update.middleware()
    async def log_updates(handler, event, data):
        if hasattr(event, 'update_id'):
            user_id = getattr(getattr(event, 'from_user', None), 'id', 'unknown')
            root_logger.info(f"Update: {event.update_id} from user {user_id}")
        return await handler(event, data)
    
    # Обработчик команды /start с главной клавиатурой
    @dp.message(CommandStart())
    async def cmd_start(message: types.Message):
        await message.answer(
            "👋 Привет! Это бот мероприятия 'Гости Небесного'.\n\nВыберите действие:",
            reply_markup=get_main_menu_reply()
        )
        root_logger.info(f"User {message.from_user.id} pressed /start")
    
    # Обработчик текстовых кнопок главного меню
    @dp.message(F.text == "👥 Посмотреть участников")
    async def view_participants_button(message: types.Message):
        await start.view_participants(message)
    
    @dp.message(F.text == "📝 Добавить анкету")
    async def add_profile_button(message: types.Message):
        await profile.start_form(message)
    
    # Запуск
    root_logger.info("Бот запущен и готов к работе...")
    print(">>> POLLING STARTED <<<", flush=True)
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        root_logger.info("Бот выключен пользователем")
    except Exception as e:
        root_logger.error(f"Критическая ошибка: {e}", exc_info=True)
        print(f">>> CRITICAL ERROR: {e} <<<", flush=True)
