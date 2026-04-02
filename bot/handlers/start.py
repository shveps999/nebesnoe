import logging
from aiogram import Router, F, types
from aiogram.types import URLInputFile
from bot.keyboards import get_main_menu_inline, get_refresh_keyboard, get_admin_keyboard
from bot.database import get_approved_profiles, user_has_approved_profile, get_user_last_message, save_user_message
from bot.config import ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

async def delete_previous_menu(bot: Bot, tg_id: int):
    """Удалить предыдущее сообщение меню"""
    last_message_id = await get_user_last_message(tg_id)
    if last_message_id:
        try:
            await bot.delete_message(chat_id=tg_id, message_id=last_message_id)
            logger.debug(f"Deleted old menu message {last_message_id} for user {tg_id}")
        except Exception as e:
            logger.debug(f"Could not delete old menu message: {e}")

async def send_main_menu(message: types.Message, bot: Bot, delete_old: bool = True):
    """Отправить главное меню с удалением старого"""
    tg_id = message.from_user.id
    has_profile = await user_has_approved_profile(tg_id)
    
    # Удаляем предыдущее меню
    if delete_old:
        await delete_previous_menu(bot, tg_id)
    
    # Отправляем новое меню и сохраняем его ID
    new_message = await message.answer(
        "🏠 **Главное меню**\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline(has_profile)
    )
    await save_user_message(tg_id, new_message.message_id)
    logger.info(f"Sent main menu to user {tg_id}, message_id={new_message.message_id}")
    return new_message

@router.callback_query(F.data == "view_participants")
async def view_participants_callback(callback: types.CallbackQuery):
    """Обработка кнопки 'Посмотреть участников'"""
    await callback.message.delete()
    await view_participants(callback.message, callback.from_user.id)
    await callback.answer()

@router.callback_query(F.data == "refresh_list")
async def refresh_list_callback(callback: types.CallbackQuery):
    """Обработка кнопки 'Обновить список'"""
    await callback.message.delete()
    await view_participants(callback.message, callback.from_user.id)
    await callback.answer("Список обновлён! 🔄")

async def view_participants(message: types.Message, user_tg_id: int = None):
    """Показать список одобренных участников"""
    if user_tg_id is None:
        user_tg_id = message.from_user.id
    
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
    
    await message.answer(
        "📋 **Конец списка.**",
        parse_mode="Markdown",
        reply_markup=get_refresh_keyboard()
    )
    
    if message.from_user.id == ADMIN_ID:
        await message.answer(
            "🔧 **Админ-панель:**",
            reply_markup=get_admin_keyboard()
        )
    
    logger.info(f"Sent {len(profiles)} profiles to user {user_tg_id}")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery, bot: Bot):
    """Вернуться в главное меню с очисткой всех сообщений"""
    tg_id = callback.from_user.id
    
    # Удаляем ВСЕ сообщения пользователя в чате с ботом
    try:
        # Получаем последние 100 сообщений (максимум API)
        messages = []
        async for msg in bot.get_chat_history(chat_id=tg_id, limit=100):
            if msg.from_user and msg.from_user.id == bot.id:
                messages.append(msg.message_id)
        
        # Удаляем все сообщения бота кроме последнего (которое будет новым меню)
        for msg_id in messages:
            try:
                await bot.delete_message(chat_id=tg_id, message_id=msg_id)
            except:
                pass
        
        logger.info(f"Deleted {len(messages)} old messages for user {tg_id}")
    except Exception as e:
        logger.error(f"Error deleting old messages: {e}")
    
    # Отправляем чистое главное меню
    await send_main_menu(callback.message, bot, delete_old=False)
    await callback.answer()
