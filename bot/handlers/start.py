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

async def _delete_participant_list(bot: Bot, user_tg_id: int):
    """Удалить список участников по сохранённому ID"""
    saved_id = await get_user_last_message(user_tg_id)
    
    if saved_id and saved_id < 0:  # Отрицательное = это был список анкет
        last_list_msg_id = abs(saved_id)
        
        # Удаляем финальное сообщение списка (с кнопками)
        await delete_message_safe(bot, user_tg_id, last_list_msg_id)
        
        # Удаляем предыдущие ~25 сообщений (анкеты + фото)
        for offset in range(1, 30):
            await delete_message_safe(bot, user_tg_id, last_list_msg_id - offset)
        
        logger.debug(f"Deleted participant list for user {user_tg_id}")

async def send_main_menu(message: types.Message, bot: Bot, user_tg_id: int, delete_old: bool = True):
    """Отправить главное меню, удалив предыдущее"""
    # Проверяем, есть ли у пользователя одобренная анкета
    has_profile = await user_has_approved_profile(user_tg_id)
    
    # Удаляем предыдущее меню если нужно
    if delete_old:
        last_menu_id = await get_user_last_message(user_tg_id)
        if last_menu_id and last_menu_id > 0:  # Положительное = меню
            await delete_message_safe(bot, user_tg_id, last_menu_id)
    
    # Отправляем новое меню
    new_message = await message.answer(
        "🏠 **Главное меню**\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline(has_profile)
    )
    
    # Сохраняем ID нового меню (положительное = меню)
    await save_user_message(user_tg_id, new_message.message_id)
    logger.info(f"Sent main menu to user {user_tg_id}, message_id={new_message.message_id}")
    return new_message

async def send_participants_list(message: types.Message, bot: Bot, user_tg_id: int):
    """Отправить список участников, удалив предыдущее меню"""
    # Удаляем предыдущее меню
    last_menu_id = await get_user_last_message(user_tg_id)
    if last_menu_id and last_menu_id > 0:  # Положительное = меню
        await delete_message_safe(bot, user_tg_id, last_menu_id)
    
    # Проверяем доступ
    if user_tg_id != ADMIN_ID:
        has_profile = await user_has_approved_profile(user_tg_id)
        if not has_profile:
            await message.answer(
                "Чтобы посмотреть список участников, "
                "сначала добавьте **свою анкету**.\n\n",
                parse_mode="Markdown",
                reply_markup=get_main_menu_inline()
            )
            logger.info(f"User {user_tg_id} tried to view participants without profile")
            return
    
    profiles = await get_approved_profiles()
    
    if not profiles:
        await message.answer(
            "Список пока пуст.\n\nБудь первым!",
            reply_markup=get_main_menu_inline()
        )
        return
    
    first_msg_id = None
    
    # Отправляем анкеты БЕЗ кнопок
    for profile in profiles:
        # Формируем строку с Telegram (кликабельная)
        tg_line = ""
        if profile.get('tg_username'):
            tg_line = f"\n\n🔗 Тг: {profile['tg_username']}"
        
        caption = (
            f"**{profile['name']}**\n\n"
            f"🪄 {profile['occupation']}\n\n"
            f"💡 Ищу: {profile['looking']}"
            f"{tg_line}"
        )
        
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
    
    # ✅ Кнопки ТОЛЬКО в конце (с минимальным текстом ".")
    final_msg = await message.answer(
        ".",  # ← точка (минимальный видимый текст)
        reply_markup=get_refresh_keyboard()
    )
    
    # Сохраняем ID последнего сообщения списка (отрицательное = список)
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
    if last_menu_id and last_menu_id > 0:
        await delete_message_safe(bot, user_tg_id, last_menu_id)
    
    # 2. Безопасно удаляем сообщение с кнопкой
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    
    # 3. Показываем список
    await send_participants_list(callback.message, bot, user_tg_id)
    await callback.answer()

@router.callback_query(F.data == "refresh_list")
async def refresh_list_callback(callback: types.CallbackQuery, bot: Bot):
    """Обновить список (удаляет старый список перед показом нового)"""
    user_tg_id = callback.from_user.id
    
    # 1. Удаляем СТАРЫЙ список участников (если есть)
    await _delete_participant_list(bot, user_tg_id)
    
    # 2. Безопасно удаляем сообщение с кнопкой "Обновить"
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    
    # 3. Показываем НОВЫЙ список
    await send_participants_list(callback.message, bot, user_tg_id)
    await callback.answer("Список обновлён! 🔄")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery, bot: Bot):
    """Вернуться в меню (удаляет список анкет и показывает чистое меню)"""
    user_tg_id = callback.from_user.id
    
    # 1. Удаляем список участников (если он был показан)
    await _delete_participant_list(bot, user_tg_id)
    
    # 2. Если был показан меню (а не список) — удаляем его
    saved_id = await get_user_last_message(user_tg_id)
    if saved_id and saved_id > 0:  # Положительное = меню
        await delete_message_safe(bot, user_tg_id, saved_id)
    
    # 3. Безопасно удаляем сообщение с кнопкой "В главное меню"
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    
    # 4. Показываем чистое меню (передаём user_tg_id явно!)
    await send_main_menu(callback.message, bot, user_tg_id, delete_old=False)
    await callback.answer()
