import logging
from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.types import URLInputFile
from bot.keyboards import get_main_menu_reply, get_refresh_keyboard
from bot.database import get_approved_profiles

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "view_participants")
async def view_participants_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    await view_participants(callback.message)
    await callback.answer()

async def view_participants(message: types.Message):
    """Показать список одобренных участников"""
    profiles = await get_approved_profiles()
    
    if not profiles:
        await message.answer(
            "📭 Пока нет одобренных анкет.\n\nБудьте первым!",
            reply_markup=get_main_menu_reply()
        )
        return
    
    await message.answer(
        f"👥 **Найдено участников: {len(profiles)}**\n\nНиже анкеты:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_reply()
    )
    
    for profile in profiles:
        caption = f"👤 **{profile['name']}**\n💼 {profile['occupation']}\n🔍 Ищет: {profile['looking']}"
        try:
            if profile['photo_url']:
                await message.answer_photo(
                    photo=URLInputFile(profile['photo_url']),
                    caption=caption,
                    parse_mode="Markdown",
                    reply_markup=get_main_menu_reply()
                )
            else:
                await message.answer(
                    caption,
                    parse_mode="Markdown",
                    reply_markup=get_main_menu_reply()
                )
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            await message.answer(caption, parse_mode="Markdown", reply_markup=get_main_menu_reply())
    
    await message.answer(
        "📋 **Конец списка.**",
        parse_mode="Markdown",
        reply_markup=get_refresh_keyboard()
    )
    logger.info(f"Sent {len(profiles)} profiles to user {message.from_user.id}")

@router.callback_query(F.data == "refresh_list")
async def refresh_list(callback: types.CallbackQuery):
    """Обновить список участников"""
    await callback.message.delete()
    await view_participants(callback.message)
    await callback.answer("Список обновлён! 🔄")
