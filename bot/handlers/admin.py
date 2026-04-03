import logging
import asyncio
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from bot.keyboards import (
    get_moderation_keyboard, get_main_menu_inline, 
    get_clear_all_confirm_keyboard, get_admin_keyboard,
    get_broadcast_cancel_keyboard, get_broadcast_confirm_keyboard
)
from bot.database import (
    get_pending_profiles, update_profile_status, get_profile_by_id, 
    get_all_approved_with_photos, delete_all_approved_profiles,
    get_all_user_tg_ids, get_approved_user_tg_ids
)
from bot.s3_storage import delete_multiple_photos_from_s3
from bot.config import ADMIN_ID, MODERATION_CHAT_ID

logger = logging.getLogger(__name__)
router = Router()

class AdminEdit(StatesGroup):
    comment = State()
    profile_id = State()

class BroadcastForm(StatesGroup):
    message = State()
    confirm = State()

# ============================================
# МОДЕРАЦИЯ АНКЕТ (ваши тексты сохранены)
# ============================================

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
            "**Твоя визитка опубликована!**\n\n"
            "Теперь ты можешь смотреть список участников.\n\n"
            "До встречи в Небесном ❤️‍🔥"
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
    
    await callback.answer("Анкета опубликована!")
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
            f"⚠️ **Организатор запросил изменения**\n\n"
            f"**Комментарий:**\n{comment}\n\n"
            f"Пожалуйста, заполни визитку заново через меню."
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

# ============================================
# РАССЫЛКА УВЕДОМЛЕНИЙ (НОВЫЙ ФУНКЦИОНАЛ)
# ============================================

@router.message(Command("broadcast"), F.from_user.id == ADMIN_ID)
async def cmd_broadcast(message: types.Message, state: FSMContext):
    """Команда начала рассылки (только для админа)"""
    await message.answer(
        "📢 **Рассылка уведомлений**\n\n"
        "Введите текст сообщения, которое нужно отправить всем пользователям бота.\n\n"
        "Поддерживается **Markdown** форматирование.\n\n"
        "❌ Нажмите /cancel для отмены",
        parse_mode="Markdown",
        reply_markup=get_broadcast_cancel_keyboard()
    )
    await state.set_state(BroadcastForm.message)
    logger.info(f"Admin {message.from_user.id} started broadcast command")

@router.callback_query(F.data == "broadcast_cancel", F.from_user.id == ADMIN_ID)
async def broadcast_cancel(callback: types.CallbackQuery, state: FSMContext):
    """Отмена рассылки"""
    await state.clear()
    await callback.message.edit_text(
        "❌ **Рассылка отменена**",
        reply_markup=get_main_menu_inline()
    )
    await callback.answer()
    logger.info(f"Admin {callback.from_user.id} cancelled broadcast")

@router.message(BroadcastForm.message, F.text)
async def broadcast_preview(message: types.Message, state: FSMContext):
    """Показать превью рассылки и запросить подтверждение"""
    text = message.text
    await state.update_data(broadcast_text=text)
    
    # Получаем количество пользователей
    all_users = await get_all_user_tg_ids()
    approved_users = await get_approved_user_tg_ids()
    
    preview = (
        f"📢 **Предпросмотр рассылки**\n\n"
        f"📝 **Текст сообщения:**\n{text}\n\n"
        f"👥 **Получатели:**\n"
        f"• Всего пользователей: **{len(all_users)}**\n"
        f"• С одобренной анкетой: **{len(approved_users)}**\n\n"
        f"Выберите кому отправить:"
    )
    
    await message.answer(
        preview,
        parse_mode="Markdown",
        reply_markup=get_broadcast_confirm_keyboard()
    )
    await state.set_state(BroadcastForm.confirm)

@router.callback_query(F.data == "broadcast_confirm", F.from_user.id == ADMIN_ID)
async def broadcast_send_all(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Отправить всем пользователям"""
    await callback.message.edit_text("⏳ **Отправка...**\n\nПожалуйста, подождите.")
    await _send_broadcast(callback, state, bot, approved_only=False)

@router.callback_query(F.data == "broadcast_approved_only", F.from_user.id == ADMIN_ID)
async def broadcast_send_approved(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    """Отправить только пользователям с одобренной анкетой"""
    await callback.message.edit_text("⏳ **Отправка...**\n\nПожалуйста, подождите.")
    await _send_broadcast(callback, state, bot, approved_only=True)

async def _send_broadcast(callback: types.CallbackQuery, state: FSMContext, bot: Bot, approved_only: bool):
    """Внутренняя функция отправки рассылки"""
    data = await state.get_data()
    text = data.get('broadcast_text')
    
    if not text:
        await callback.message.edit_text("❌ **Ошибка:** Текст сообщения не найден.")
        await state.clear()
        return
    
    # Получаем список пользователей
    if approved_only:
        user_ids = await get_approved_user_tg_ids()
        target = "с одобренной анкетой"
    else:
        user_ids = await get_all_user_tg_ids()
        target = "всем"
    
    if not user_ids:
        await callback.message.edit_text(f"❌ **Нет пользователей** {target} для рассылки.")
        await state.clear()
        return
    
    # Счётчики
    sent = 0
    failed = 0
    blocked = 0
    
    # Отправляем каждому пользователю
    for user_id in user_ids:
        try:
            await bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="Markdown"
            )
            sent += 1
            await asyncio.sleep(0.05)  # Небольшая задержка чтобы не получить бан
        except Exception as e:
            error_str = str(e).lower()
            if "forbidden" in error_str or "blocked" in error_str:
                blocked += 1
            else:
                failed += 1
            logger.warning(f"Failed to send to {user_id}: {e}")
    
    # Отчёт админу
    report = (
        f"✅ **Рассылка завершена!**\n\n"
        f"📊 **Статистика:**\n"
        f"• Получателей: **{len(user_ids)}** ({target})\n"
        f"• ✅ Доставлено: **{sent}**\n"
        f"• ❌ Ошибок: **{failed}**\n"
        f"• 🚫 Заблокировали бота: **{blocked}**"
    )
    
    await callback.message.edit_text(
        report,
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    
    await state.clear()
    logger.info(f"Broadcast completed by admin {callback.from_user.id}: sent={sent}, failed={failed}, blocked={blocked}")
