import logging
from aiogram import Router, F, types, Bot
from aiogram.types import URLInputFile
from bot.keyboards import get_main_menu_inline, get_refresh_keyboard, get_admin_keyboard, get_consent_keyboard
from bot.database import get_approved_profiles, user_has_approved_profile, get_user_last_message, save_user_message, user_has_consented, save_user_consent
from bot.config import ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

PRIVACY_POLICY_URL = "https://clck.ru/3SvSMd"

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
    
    if saved_id and saved_id < 0:
        last_list_msg_id = abs(saved_id)
        await delete_message_safe(bot, user_tg_id, last_list_msg_id)
        for offset in range(1, 30):
            await delete_message_safe(bot, user_tg_id, last_list_msg_id - offset)
        logger.debug(f"Deleted participant list for user {user_tg_id}")

async def send_main_menu(message: types.Message, bot: Bot, user_tg_id: int, delete_old: bool = True):
    """Отправить главное меню, удалив предыдущее"""
    has_profile = await user_has_approved_profile(user_tg_id)
    
    if delete_old:
        last_menu_id = await get_user_last_message(user_tg_id)
        if last_menu_id and last_menu_id > 0:
            await delete_message_safe(bot, user_tg_id, last_menu_id)
    
    new_message = await message.answer(
        "🪩 **Тусовка Небесного**\n\nВыбери действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline(has_profile)
    )
    
    await save_user_message(user_tg_id, new_message.message_id)
    logger.info(f"Sent main menu to user {user_tg_id}, message_id={new_message.message_id}")
    return new_message

async def show_consent_flow(message: types.Message, bot: Bot):
    """Показать поток согласия на обработку данных"""
    tg_id = message.from_user.id
    
    welcome = await message.answer(
        "Привет! Рады видеть тебя в нашем боте, сейчас все покажем ✨"
    )
    
    consent_text = (
        "Перед тем, как начать, нам нужно получить твое согласие на обработку персональных данных:\n\n"
        "🔹 Собираем: имя, сферу деятельности, кого ищете, фото, никнейм в тг\n"
        "🔹 Удалить анкету: через меню «Управление анкетой» → «Удалить анкету»\n"
        "🔹 Перед каждым новым ивентом — удаляется автоматически\n\n"
        f"Нажимая «Я согласен», вы принимаете условия [Политики обработки персональных данных]({PRIVACY_POLICY_URL})."
    )
    
    consent_msg = await message.answer(
        consent_text,
        parse_mode="Markdown",
        disable_web_page_preview=False,
        reply_markup=get_consent_keyboard()
    )
    
    await save_user_message(tg_id, -consent_msg.message_id)
    logger.info(f"Shown consent flow to user {tg_id}")

async def send_participants_list(message: types.Message, bot: Bot, user_tg_id: int):
    """Отправить список участников, удалив предыдущее меню"""
    last_menu_id = await get_user_last_message(user_tg_id)
    if last_menu_id and last_menu_id > 0:
        await delete_message_safe(bot, user_tg_id, last_menu_id)
    
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
    
    for profile in profiles:
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
    
    final_msg = await message.answer(
        ".",
        reply_markup=get_refresh_keyboard()
    )
    
    await save_user_message(user_tg_id, -final_msg.message_id)
    
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
    
    if not await user_has_consented(user_tg_id):
        await callback.answer("⚠️ Сначала дайте согласие на обработку данных", show_alert=True)
        return
    
    last_menu_id = await get_user_last_message(user_tg_id)
    if last_menu_id and last_menu_id > 0:
        await delete_message_safe(bot, user_tg_id, last_menu_id)
    
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    await send_participants_list(callback.message, bot, user_tg_id)
    await callback.answer()

@router.callback_query(F.data == "refresh_list")
async def refresh_list_callback(callback: types.CallbackQuery, bot: Bot):
    """Обновить список (удаляет старый список перед показом нового)"""
    user_tg_id = callback.from_user.id
    
    if not await user_has_consented(user_tg_id):
        await callback.answer("⚠️ Сначала дайте согласие на обработку данных", show_alert=True)
        return
    
    await _delete_participant_list(bot, user_tg_id)
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    await send_participants_list(callback.message, bot, user_tg_id)
    await callback.answer("Список обновлён! 🔄")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery, bot: Bot):
    """Вернуться в меню (удаляет список анкет и показывает чистое меню)"""
    user_tg_id = callback.from_user.id
    
    if not await user_has_consented(user_tg_id):
        await callback.answer("⚠️ Сначала дайте согласие на обработку данных", show_alert=True)
        return
    
    await _delete_participant_list(bot, user_tg_id)
    
    saved_id = await get_user_last_message(user_tg_id)
    if saved_id and saved_id > 0:
        await delete_message_safe(bot, user_tg_id, saved_id)
    
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    await send_main_menu(callback.message, bot, user_tg_id, delete_old=False)
    await callback.answer()

@router.callback_query(F.data == "consent_agree")
async def consent_agree_callback(callback: types.CallbackQuery, bot: Bot):
    """Обработка согласия на обработку данных"""
    user_tg_id = callback.from_user.id
    
    await save_user_consent(user_tg_id)
    
    saved_id = await get_user_last_message(user_tg_id)
    if saved_id and saved_id < 0:
        consent_msg_id = abs(saved_id)
        await delete_message_safe(bot, user_tg_id, consent_msg_id)
        await delete_message_safe(bot, user_tg_id, consent_msg_id - 1)
    
    await send_main_menu(callback.message, bot, user_tg_id, delete_old=False)
    await callback.answer()
    logger.info(f"User {user_tg_id} gave consent to data processing")
