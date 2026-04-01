import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from bot.config import BOT_TOKEN
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
    
    # Middleware для логирования
    @dp.middleware()
    async def log_updates(handler, event, data):
        if hasattr(event, 'update_id'):
            root_logger.info(f"Update: {event.update_id}")
        return await handler(event, data)
    
    # Команда /start с главной клавиатурой
    @dp.message(CommandStart())
    async def cmd_start(message: types.Message):
        await message.answer(
            "👋 Привет! Это бот мероприятия 'Гости Небесного'.\n\nВыберите действие:",
            reply_markup=get_main_menu_reply()
        )
        root_logger.info(f"User {message.from_user.id} pressed /start")
    
    # Запуск
    root_logger.info("Бот запущен и готов к работе...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        root_logger.info("Бот выключен пользователем")
    except Exception as e:
        root_logger.error(f"Критическая ошибка: {e}", exc_info=True)
