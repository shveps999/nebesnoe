import logging
from aiogram import Router, F, types, Bot
from aiogram.types import URLInputFile
from bot.keyboards import get_main_menu_inline, get_refresh_keyboard, get_admin_keyboard
from bot.database import get_approved_profiles, user_has_approved_profile, get_user_last_message, save_user_message
from bot.config import ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

async def delete_message_safe(bot: Bot, chat_id: int, message_id: int):
    """Безопасное удаление сообщения (игнорирует ошибки)"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass  # Сообщение уже удалено или не существует

async def send_main_menu(message: types.Message, bot: Bot, delete_old: bool = True):
    """Отправить главное меню, удалив предыдущее"""
    tg_id = message.from_user.id
    
    # Удаляем предыдущее меню если нужно
    if delete_old:
        last_menu_id = await get_user_last_message(tg_id)
        if last_menu_id:
            await delete_message_safe(bot, tg_id, last_menu_id)
    
    # Отправляем новое меню
    new_message = await message.answer(
        "🏠 **Главное меню**\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline(await user_has_approved_profile(tg_id))
    )
    
    # Сохраняем ID нового меню
    await save_user_message(tg_id, new_message.message_id)
    logger.info(f"Sent main menu to user {tg_id}, message_id={new_message.message_id}")
    return new_message

async def send_participants_list(message: types.Message, bot: Bot, user_tg_id: int):
    """Отправить список участников, удалив предыдущее меню"""
    # Удаляем предыдущее меню
    last_menu_id = await get_user_last_message(user_tg_id)
    if last_menu_id:
        await delete_message_safe(bot, user_tg_id, last_menu_id)
    
    # Проверяем доступ
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
    
    # Отправляем анкеты БЕЗ кнопок
    for profile in profiles:
        caption = f"👤 **{profile['name']}**\n💼 {profile['occupation']}\n🔍 Ищет: {profile['looking']}"
        try:
            if profile['photo_url']:
                await message.answer_photo(
                    photo=URLInputFile(profile['photo_url']),
                    caption=caption,
                    parse_mode="Markdown"
                )
            else:
                await message.answer(
                    caption,
                    parse_mode="Markdown"
                )
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            await message.answer(caption, parse_mode="Markdown")
    
    # Кнопки ТОЛЬКО в конце
    final_msg = await message.answer(
        "📋 **Конец списка.**",
        parse_mode="Markdown",
        reply_markup=get_refresh_keyboard()
    )
    
    # Если админ - показываем админ-панель
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "🔧 **Админ-панель:**",
            reply_markup=get_admin_keyboard()
        )
    
    logger.info(f"Sent {len(profiles)} profiles to user {user_tg_id}")
    return final_msg

@router.callback_query(F.data == "view_participants")
async def view_participants_callback(callback: types.CallbackQuery, bot: Bot):
    """Показать список участников (удаляет меню)"""
    await callback.message.delete()  # Удаляем нажатую кнопку/меню
    await send_participants_list(callback.message, bot, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "refresh_list")
async def refresh_list_callback(callback: types.CallbackQuery, bot: Bot):
    """Обновить список (удаляет старый, показывает новый)"""
    # Удаляем все сообщения списка (последние ~50)
    try:
        async for msg in bot.get_chat_history(chat_id=callback.from_user.id, limit=50):
            if msg.from_user and msg.from_user.id == bot.id and msg.text and "Конец списка" in msg.text:
                await delete_message_safe(bot, callback.from_user.id, msg.message_id)
                break
    except:
        pass
    
    await send_participants_list(callback.message, bot, callback.from_user.id)
    await callback.answer("Список обновлён! 🔄")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery, bot: Bot):
    """Вернуться в меню (удаляет ВСЁ и показывает чистое меню)"""
    tg_id = callback.from_user.id
    
    # Удаляем ВСЕ сообщения бота в чате (максимум 100)
    try:
        async for msg in bot.get_chat_history(chat_id=tg_id, limit=100):
            if msg.from_user and msg.from_user.id == bot.id:
                await delete_message_safe(bot, tg_id, msg.message_id)
    except Exception as e:
        logger.error(f"Error cleaning chat: {e}")
    
    # Показываем чистое меню
    await send_main_menu(callback.message, bot, delete_old=False)
    await callback.answer()
