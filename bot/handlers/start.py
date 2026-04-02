import logging
from aiogram import Router, F, types
from aiogram.types import URLInputFile
from bot.keyboards import get_main_menu_inline, get_refresh_keyboard, get_admin_keyboard
from bot.database import get_approved_profiles, user_has_approved_profile
from bot.config import ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "view_participants")
async def view_participants_callback(callback: types.CallbackQuery):
    """Обработка кнопки 'Посмотреть участников'"""
    await callback.message.delete()
    await view_participants(callback.message)
    await callback.answer()

@router.callback_query(F.data == "refresh_list")
async def refresh_list_callback(callback: types.CallbackQuery):
    """Обработка кнопки 'Обновить список'"""
    await callback.message.delete()
    await view_participants(callback.message)
    await callback.answer("Список обновлён! 🔄")

async def view_participants(message: types.Message):
    """Показать список одобренных участников"""
    user_tg_id = message.from_user.id
    
    # Проверяем, есть ли у пользователя одобренная анкета
    if user_tg_id != ADMIN_ID:
        has_profile = await user_has_approved_profile(user_tg_id)
        
        if not has_profile:
            await message.answer(
                "⛔ **Доступ ограничен**\n\n"
                "Чтобы просматривать анкеты других участников, "
                "сначала добавьте **свою анкету**.\n\n"
                "Это необходимо для поддержания активности в сообществе.",
                parse_mode="Markdown",
                reply_markup=get_main_menu_inline()
            )
            logger.info(f"User {user_tg_id} tried to view participants without profile")
            return
    
    profiles = await get_approved_profiles()
    
    if not profiles:
        await message.answer(
            "📭 Пока нет одобренных анкет.\n\nБудьте первым!",
            reply_markup=get_main_menu_inline()
        )
        return
    
    # Отправляем все анкеты БЕЗ кнопок
    for profile in profiles:
        caption = f"👤 **{profile['name']}**\n💼 {profile['occupation']}\n🔍 Ищет: {profile['looking']}"
        try:
            if profile['photo_url']:
                await message.answer_photo(
                    photo=URLInputFile(profile['photo_url']),
                    caption=caption,
                    parse_mode="Markdown"
                    # НЕТ reply_markup здесь!
                )
            else:
                await message.answer(
                    caption,
                    parse_mode="Markdown"
                    # НЕТ reply_markup здесь!
                )
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            await message.answer(caption, parse_mode="Markdown")
    
    # Кнопки только в КОНЦЕ после всех анкет
    await message.answer(
        "📋 **Конец списка.**",
        parse_mode="Markdown",
        reply_markup=get_refresh_keyboard()
    )
    
    # Если админ - показать кнопку админ-панели
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "🔧 **Админ-панель:**",
            reply_markup=get_admin_keyboard()
        )
    
    logger.info(f"Sent {len(profiles)} profiles to user {message.from_user.id}")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    """Вернуться в главное меню"""
    await callback.message.delete()
    has_profile = await user_has_approved_profile(callback.from_user.id)
    await callback.message.answer(
        "🏠 **Главное меню**",
        reply_markup=get_main_menu_inline(has_profile)
    )
    await callback.answer()
