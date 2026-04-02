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
        logger.debug(f"Deleted message {message_id} in chat {chat_id}")
    except Exception as e:
        logger.debug(f"Could not delete message {message_id}: {e}")

async def send_main_menu(message: types.Message, bot: Bot, delete_old: bool = True):
    """Отправить главное меню, удалив предыдущее"""
    tg_id = message.from_user.id
    
    # Проверяем, есть ли у пользователя одобренная анкета
    has_profile = await user_has_approved_profile(tg_id)
    
    # Удаляем предыдущее меню если нужно
    if delete_old:
        last_menu_id = await get_user_last_message(tg_id)
        if last_menu_id:
            await delete_message_safe(bot, tg_id, last_menu_id)
    
    # Отправляем новое меню
    new_message = await message.answer(
        "🏠 **Главное меню**\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline(has_profile)
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
    
    first_msg_id = None
    
    # Отправляем анкеты БЕЗ кнопок
    for profile in profiles:
        caption = f"👤 **{profile['name']}**\n💼 {profile['occupation']}\n🔍 Ищет: {profile['looking']}"
        try:
            if profile['photo_url']:
                sent_msg = await message.answer_photo(
                    photo=URLInputFile(profile['photo_url']),
                    caption=caption,
                    parse_mode="Markdown"
                )
            else:
                sent_msg = await message.answer(
                    caption,
                    parse_mode="Markdown"
                )
            
            if first_msg_id is None:
                first_msg_id = sent_msg.message_id
                
        except Exception as e:
            logger.error(f"Ошибка отправки фото: {e}")
            sent_msg = await message.answer(caption, parse_mode="Markdown")
            if first_msg_id is None:
                first_msg_id = sent_msg.message_id
    
    # Кнопки ТОЛЬКО в конце
    final_msg = await message.answer(
        "📋 **Конец списка.**",
        parse_mode="Markdown",
        reply_markup=get_refresh_keyboard()
    )
    
    # Сохраняем ID последнего сообщения списка (для удаления при возврате в меню)
    # Используем отрицательное значение как маркер "это список, а не меню"
    await save_user_message(user_tg_id, -final_msg.message_id)
    
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
    user_tg_id = callback.from_user.id
    
    # 1. Удаляем предыдущее меню
    last_menu_id = await get_user_last_message(user_tg_id)
    if last_menu_id and last_menu_id > 0:  # Положительное = меню
        await delete_message_safe(bot, user_tg_id, last_menu_id)
    
    # 2. Безопасно удаляем сообщение с кнопкой
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    
    # 3. Показываем список
    await send_participants_list(callback.message, bot, user_tg_id)
    await callback.answer()

@router.callback_query(F.data == "refresh_list")
async def refresh_list_callback(callback: types.CallbackQuery, bot: Bot):
    """Обновить список"""
    user_tg_id = callback.from_user.id
    
    # Безопасно удаляем предыдущее сообщение с кнопками
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    
    # Показываем новый список
    await send_participants_list(callback.message, bot, user_tg_id)
    await callback.answer("Список обновлён! 🔄")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery, bot: Bot):
    """Вернуться в меню (удаляет список анкет и показывает чистое меню)"""
    user_tg_id = callback.from_user.id
    
    # 1. Получаем сохранённый ID (может быть отрицательным = список)
    saved_id = await get_user_last_message(user_tg_id)
    
    if saved_id and saved_id < 0:  # Отрицательное = это был список анкет
        last_list_msg_id = abs(saved_id)
        
        # Удаляем финальное сообщение списка (с кнопками)
        await delete_message_safe(bot, user_tg_id, last_list_msg_id)
        
        # Удаляем предыдущие ~20 сообщений (анкеты) - сообщение в чате имеют последовательные ID
        for offset in range(1, 25):
            await delete_message_safe(bot, user_tg_id, last_list_msg_id - offset)
    
    elif saved_id and saved_id > 0:  # Положительное = это было меню
        await delete_message_safe(bot, user_tg_id, saved_id)
    
    # 2. Безопасно удаляем сообщение с кнопкой "В главное меню"
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    
    # 3. Показываем чистое меню
    await send_main_menu(callback.message, bot, delete_old=False)
    await callback.answer()
