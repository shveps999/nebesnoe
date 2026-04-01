import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher
from bot.config import BOT_TOKEN
from bot.database import init_db
from bot.handlers import start, profile, admin

# Создание папки для логов
os.makedirs("logs", exist_ok=True)

# Настройка логирования: вывод и в файл, и в консоль (для journalctl)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)

async def main():
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher()
    
    # Инициализация БД
    await init_db()
    logging.info("База данных инициализирована")
    
    # Регистрация роутеров
    dp.include_router(start.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)
    
    # Запуск
    logging.info("Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот выключен")
