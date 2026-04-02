import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from bot.keyboards import get_moderation_keyboard, get_main_menu_inline, get_clear_all_confirm_keyboard, get_admin_keyboard
from bot.database import get_pending_profiles, update_profile_status, get_profile_by_id, get_all_approved_with_photos, delete_all_approved_profiles
from bot.s3_storage import delete_multiple_photos_from_s3
from bot.config import ADMIN_ID, MODERATION_CHAT_ID

logger = logging.getLogger(__name__)
router = Router()

class AdminEdit(StatesGroup):
    comment = State()
    profile_id = State()

@router.message(Command("clear_all"), F.from_user.id == ADMIN_ID)
async def cmd_clear_all(message: types.Message):
    """Команда для удаления всех опубликованных анкет"""
    await message.answer(
        "⚠️ **ВНИМАНИЕ!**\n\n"
        "Вы собираетесь удалить **ВСЕ опубликованные анкеты**:\n"
        "• Из базы данных\n"
        "• Фото из хранилища S3\n\n"
        "Это действие **НЕЛЬЗЯ ОТМЕНИТЬ**!\n\n"
        "Подтвердите удаление:",
        parse_mode="Markdown",
        reply_markup=get_clear_all_confirm_keyboard()
    )
    logger.info(f"Admin {message.from_user.id} initiated clear_all command")

@router.callback_query(F.data == "clear_all_confirm")
async def clear_all_confirm(callback: types.CallbackQuery, bot: Bot):
    """Подтверждение удаления всех анкет"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "⏳ **Удаление...**\n\nПожалуйста, подождите.",
        parse_mode="Markdown"
    )
    
    try:
        profiles = await get_all_approved_with_photos()
        photo_urls = [p['photo_url'] for p in profiles if p['photo_url']]
        
        s3_stats = {'success': 0, 'failed': 0}
        if photo_urls:
            s3_stats = await delete_multiple_photos_from_s3(photo_urls)
        
        deleted_count = await delete_all_approved_profiles()
        
        report = (
            "✅ **Удаление завершено!**\n\n"
            f"🗑️ Удалено анкет из БД: **{deleted_count}**\n"
            f"📸 Удалено фото из S3: **{s3_stats['success']}**\n"
            f"❌ Ошибок при удалении фото: **{s3_stats['failed']}**"
        )
        
        await callback.message.edit_text(
            report,
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline()
        )
        
        logger.info(f"Admin {callback.from_user.id} cleared {deleted_count} profiles. S3: {s3_stats}")
        
    except Exception as e:
        logger.error(f"Ошибка при очистке: {e}")
        await callback.message.edit_text(
            f"❌ **Ошибка при удалении:**\n\n{str(e)}",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline()
        )
    
    await callback.answer()

@router.callback_query(F.data == "clear_all_cancel")
async def clear_all_cancel(callback: types.CallbackQuery):
    """Отмена удаления всех анкет"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    await callback.message.edit_text(
        "❌ **Удаление отменено.**",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    await callback.answer()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: types.CallbackQuery):
    """Показать статистику по анкетам"""
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("❌ Доступ запрещен", show_alert=True)
        return
    
    approved = await get_approved_profiles()
    pending = await get_pending_profiles()
    
    stats = (
        "📊 **Статистика анкет**\n\n"
        f"✅ Одобрено: **{len(approved)}**\n"
        f"⏳ На модерации: **{len(pending)}**\n"
        f"📈 Всего: **{len(approved) + len(pending)}**"
    )
    
    await callback.message.answer(
        stats,
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    await callback.answer()

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
    
    await bot.send_message(
        chat_id=profile['tg_id'],
        text=(
            "✅ **Ваша анкета одобрена!**\n\n"
            "Теперь вы можете просматривать анкеты других участников.\n\n"
            "Спасибо за участие! 🎉"
        ),
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline(has_profile=True)
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
        await message.answer("❌ Ошибка: профиль не найден.", reply_markup=get_main_menu_inline())
        await state.clear()
        return
    
    profile = await get_profile_by_id(profile_id)
    if not profile:
        await message.answer("❌ Ошибка: профиль не найден в БД.", reply_markup=get_main_menu_inline())
        await state.clear()
        return
    
    comment = message.text
    
    await update_profile_status(profile_id, 'pending', comment)
    
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
        await callback.message.delete()
        logger.info(f"Moderation message {callback.message.message_id} deleted after edit request")
    except Exception as e:
        logger.error(f"Не удалось удалить сообщение модерации: {e}")
    
    await message.answer("✅ **Сообщение отправлено пользователю!**", reply_markup=get_main_menu_inline())
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
