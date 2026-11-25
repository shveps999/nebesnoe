import logging
from aiogram import Router, F, types
from aiogram.filters import Command
from bot.config import ADMIN_ID
from bot.database import get_bot_stats

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("stats"), F.from_user.id == ADMIN_ID)
async def cmd_stats(message: types.Message):
    """Сводная статистика бота (только админ)"""
    try:
        s = await get_bot_stats()
    except Exception as e:
        logger.error(f"stats: ошибка получения статистики: {e}")
        await message.answer(
            "❌ Не удалось получить статистику. Смотри logs/bot.log",
            parse_mode=None
        )
        return

    text = (
        "📊 **Статистика бота**\n\n"
        "👥 **Пользователи**\n"
        f"• Всего (дали согласие): **{s['users_total']}**\n"
        f"• Новых за 7 дней: **{s['users_new_7d']}**\n"
        f"• С анкетой: **{s['users_with_profile']}**\n"
        f"• Без анкеты: **{s['users_without_profile']}**\n\n"
        "📋 **Анкеты**\n"
        f"• ✅ Опубликовано: **{s['approved']}**\n"
        f"• ⏳ На модерации: **{s['pending']}**\n\n"
        "📢 **Аудитория рассылки** (/broadcast)\n"
        f"• «Отправить всем»: **{s['broadcast_all']}** получателей\n"
        f"• «Только с анкетой»: **{s['broadcast_approved']}** получателей\n\n"
        "ℹ️ Пользователи = все, кто нажал «Согласен», в т.ч. без анкеты.\n"
        "Кто заблокировал бота — видно в отчёте рассылки (🚫)."
    )
    await message.answer(text, parse_mode="Markdown")
    logger.info(f"Admin {message.from_user.id} requested stats")
