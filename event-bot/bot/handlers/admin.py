import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from bot.keyboards import get_moderation_keyboard
from bot.database import get_pending_profiles, update_profile_status, get_profile_by_id
from bot.config import ADMIN_ID

router = Router()

class AdminEdit(StatesGroup):
    comment = State()

@router.message(Command("pending"), F.from_user.id == ADMIN_ID)
async def show_pending(message: types.Message, bot: Bot):
    """Команда для админа: показать все ожидающие анкеты"""
    profiles = await get_pending_profiles()
    if not profiles:
        await message.answer("Нет анкет на модерации.")
        return
    
    for profile in profiles:
        text = f"🔔 **Анкета #{profile['id']}**\nИмя: {profile['name']}\nЗанятие: {profile['occupation']}\nИщет: {profile['looking']}"
        if profile['photo_url']:
            await bot.send_photo(
                ADMIN_ID,
                photo=profile['photo_url'],
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile['id'])
            )
        else:
            await bot.send_message(
                ADMIN_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile['id'])
            )
    await message.answer("Все анкеты отправлены.")

@router.callback_query(F.data.startswith("admin_approve_"))
async def admin_approve(callback: types.CallbackQuery, bot: Bot):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    profile_id = int(callback.data.split("_")[-1])
    profile = await get_profile_by_id(profile_id)
    
    if not profile:
        await callback.answer("Анкета не найдена", show_alert=True)
        return
    
    await update_profile_status(profile_id, 'approved')
    await bot.send_message(profile['tg_id'], "✅ Ваша анкета одобрена и опубликована!")
    
    await callback.message.edit_caption(
        caption=callback.message.caption + "\n\n✅ **ОДОБРЕНО**",
        parse_mode="Markdown"
    )
    await callback.answer("Одобрено")

@router.callback_query(F.data.startswith("admin_edit_"))
async def admin_edit_request(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("Доступ запрещен", show_alert=True)
        return
    
    profile_id = int(callback.data.split("_")[-1])
    await state.update_data(profile_id=profile_id)
    await callback.message.answer("Введите комментарий для пользователя (что исправить):")
    await state.set_state(AdminEdit.comment)
    await callback.answer()

@router.message(AdminEdit.comment, F.text)
async def admin_send_comment(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    profile_id = data.get('profile_id')
    
    if not profile_id:
        await message.answer("Ошибка: профиль не найден.")
        await state.clear()
        return
    
    profile = await get_profile_by_id(profile_id)
    if not profile:
        await message.answer("Ошибка: профиль не найден в БД.")
        await state.clear()
        return
    
    comment = message.text
    await update_profile_status(profile_id, 'pending', comment)
    
    await bot.send_message(
        profile['tg_id'],
        f"⚠️ Администратор запросил изменения в анкете.\n\n💬 Комментарий: {comment}\n\nЗаполните анкету заново через меню."
    )
    await message.answer("Сообщение пользователю отправлено.")
    await state.clear()
