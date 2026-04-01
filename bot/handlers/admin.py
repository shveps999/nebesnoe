import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_moderation_keyboard, get_main_menu_inline
from bot.database import get_pending_profiles, update_profile_status, get_profile_by_id
from bot.config import ADMIN_ID, MODERATION_CHAT_ID

logger = logging.getLogger(__name__)
router = Router()

class AdminEdit(StatesGroup):
    comment = State()
    profile_id = State()

@router.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve(callback: types.CallbackQuery, bot: Bot):
    """Одобрить анкету + УДАЛИТЬ сообщение модерации"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    profile_id = int(callback.data.split("_")[-1])
    profile = await get_profile_by_id(profile_id)
    
    if not profile:
        await callback.answer("❌ Анкета не найдена", show_alert=True)
        return
    
    await update_profile_status(profile_id, 'approved')
    
    # Уведомить пользователя
    await bot.send_message(
        chat_id=profile['tg_id'],
        text=(
            "✅ **Ваша анкета одобрена!**\n\n"
            "Теперь её видят все участники мероприятия.\n\n"
            "Спасибо за участие! 🎉"
        ),
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    
    # УДАЛИТЬ сообщение модерации из чата
    try:
        await callback.message.delete()
        logger.info(f"Moderation message {callback.message.message_id} deleted after approval")
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение модерации: {e}")
    
    await callback.answer("✅ Анкета одобрена и опубликована!")
    logger.info(f"Profile {profile_id} approved by admin {callback.from_user.id}")

@router.callback_query(F.data.startswith("admin_edit_"))
async def admin_edit_request(callback: types.CallbackQuery, state: FSMContext):
    """Запросить изменения"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    profile_id = int(callback.data.split("_")[-1])
    await state.update_data(profile_id=profile_id)
    
    await callback.message.answer(
        "✏️ **Введите комментарий для пользователя**\n\n"
        "Что нужно исправить в анкете?",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    await state.set_state(AdminEdit.comment)
    await callback.answer()

@router.message(AdminEdit.comment, F.text)
async def admin_send_comment(message: types.Message, state: FSMContext, bot: Bot):
    """Отправить комментарий пользователю + УДАЛИТЬ сообщение модерации"""
    data = await state.get_data()
    profile_id = data.get('profile_id')
    
    if not profile_id:
        await message.answer(
            "❌ Ошибка: профиль не найден.",
            reply_markup=get_main_menu_inline()
        )
        await state.clear()
        return
    
    profile = await get_profile_by_id(profile_id)
    if not profile:
        await message.answer(
            "❌ Ошибка: профиль не найден в БД.",
            reply_markup=get_main_menu_inline()
        )
        await state.clear()
        return
    
    comment = message.text
    
    # Обновить статус (остаётся pending для повторной подачи)
    await update_profile_status(profile_id, 'pending', comment)
    
    # Уведомить пользователя
    await bot.send_message(
        chat_id=profile['tg_id'],
        text=(
            f"⚠️ **Администратор запросил изменения**\n\n"
            f"💬 **Комментарий:**\n{comment}\n\n"
            f"Пожалуйста, заполните анкету заново через меню."
        ),
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    
    # УДАЛИТЬ сообщение модерации из чата
    try:
        # Найти и удалить оригинальное сообщение модерации
        await callback.message.delete()
        logger.info(f"Moderation message {callback.message.message_id} deleted after edit request")
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение модерации: {e}")
    
    await message.answer(
        "✅ **Сообщение отправлено пользователю!**",
        reply_markup=get_main_menu_inline()
    )
    
    await state.clear()
    logger.info(f"Comment sent to user {profile['tg_id']} for profile {profile_id}")

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery):
    """Вернуться в главное меню"""
    await callback.message.delete()
    await callback.message.answer(
        "🏠 **Главное меню**",
        reply_markup=get_main_menu_inline()
    )
    await callback.answer()
