import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_cancel_keyboard, get_main_menu_inline, get_manage_profile_keyboard, get_confirm_delete_keyboard
from bot.database import add_profile, update_profile, user_has_approved_profile, get_profile_by_tg_id, delete_profile_by_tg_id, update_profile_status
from bot.config import ADMIN_ID, MODERATION_CHAT_ID
from bot.s3_storage import upload_photo_to_s3, delete_photo_from_s3
from bot.keyboards import get_moderation_keyboard
from aiogram.types import URLInputFile
from bot.handlers.start import send_main_menu

logger = logging.getLogger(__name__)
router = Router()

class ProfileForm(StatesGroup):
    name = State()
    occupation = State()
    looking = State()
    photo = State()

class EditForm(StatesGroup):
    profile_id = State()
    name = State()
    occupation = State()
    looking = State()
    photo = State()

@router.callback_query(F.data == "add_profile")
async def add_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Добавить анкету'"""
    has_profile = await user_has_approved_profile(callback.from_user.id)
    
    if has_profile:
        await callback.message.answer(
            "ℹ️ **У вас уже есть одобренная анкета**\n\n"
            "Вы можете просматривать анкеты других участников.\n\n"
            "Если хотите обновить информацию — используйте **Управление анкетой**.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline(has_profile=True)
        )
        await callback.answer()
        return
    
    await callback.message.delete()
    await start_form(callback.message, state)
    await callback.answer()

@router.callback_query(F.data == "manage_profile")
async def manage_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    """Обработка кнопки 'Управление анкетой'"""
    has_profile = await user_has_approved_profile(callback.from_user.id)
    
    if not has_profile:
        await callback.message.answer(
            "❌ У вас нет одобренной анкеты.",
            reply_markup=get_main_menu_inline()
        )
        await callback.answer()
        return
    
    await callback.message.delete()
    await callback.message.answer(
        "⚙️ **Управление анкетой**\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_manage_profile_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "edit_profile")
async def edit_profile_callback(callback: types.CallbackQuery, state: FSMContext):
    """Начало редактирования анкеты"""
    profile = await get_profile_by_tg_id(callback.from_user.id)
    
    if not profile or profile['status'] != 'approved':
        await callback.message.answer(
            "❌ У вас нет одобренной анкеты для редактирования.",
            reply_markup=get_main_menu_inline()
        )
        await callback.answer()
        return
    
    await state.update_data(profile_id=profile['id'])
    await callback.message.delete()
    await callback.message.answer(
        f"✏️ **Редактирование анкеты**\n\n"
        f"Текущее имя: {profile['name']}\n\n"
        f"Введите **новое имя** (или напишите 'оставить' чтобы не менять):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditForm.name)
    await callback.answer()

@router.callback_query(F.data == "delete_profile")
async def delete_profile_callback(callback: types.CallbackQuery):
    """Подтверждение удаления анкеты"""
    has_profile = await user_has_approved_profile(callback.from_user.id)
    
    if not has_profile:
        await callback.message.answer(
            "❌ У вас нет одобренной анкеты.",
            reply_markup=get_main_menu_inline()
        )
        await callback.answer()
        return
    
    await callback.message.delete()
    await callback.message.answer(
        "⚠️ **Удаление анкеты**\n\n"
        "Вы уверены, что хотите удалить свою анкету?\n\n"
        "Это действие **нельзя отменить**.",
        parse_mode="Markdown",
        reply_markup=get_confirm_delete_keyboard()
    )
    await callback.answer()

@router.callback_query(F.data == "delete_profile_confirm")
async def delete_profile_confirm(callback: types.CallbackQuery, bot: Bot):
    """Подтверждение удаления анкеты"""
    profile = await get_profile_by_tg_id(callback.from_user.id)
    
    if not profile:
        await callback.message.answer(
            "❌ Анкета не найдена.",
            reply_markup=get_main_menu_inline()
        )
        await callback.answer()
        return
    
    # Удаляем фото из S3
    if profile['photo_url']:
        await delete_photo_from_s3(profile['photo_url'])
    
    # Удаляем из БД
    deleted_count, _ = await delete_profile_by_tg_id(callback.from_user.id)
    
    await callback.message.delete()
    await callback.message.answer(
        "✅ **Анкета удалена**\n\n"
        "Ваша анкета удалена из базы данных и хранилища.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    
    logger.info(f"User {callback.from_user.id} deleted their profile")
    await callback.answer()

@router.message(EditForm.name, F.text)
async def edit_process_name(message: types.Message, state: FSMContext):
    if message.text.lower() == 'оставить':
        profile = await get_profile_by_tg_id(message.from_user.id)
        await state.update_data(name=profile['name'] if profile else '')
    else:
        await state.update_data(name=message.text.strip())
    
    await message.answer(
        "✅ Имя принято.\n\n"
        "Чем вы занимаетесь? (или напишите 'оставить' чтобы не менять):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditForm.occupation)

@router.message(EditForm.occupation, F.text)
async def edit_process_occupation(message: types.Message, state: FSMContext):
    if message.text.lower() == 'оставить':
        profile = await get_profile_by_tg_id(message.from_user.id)
        await state.update_data(occupation=profile['occupation'] if profile else '')
    else:
        await state.update_data(occupation=message.text.strip())
    
    await message.answer(
        "✅ Принято.\n\n"
        "Кого или что вы ищете? (или напишите 'оставить' чтобы не менять):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditForm.looking)

@router.message(EditForm.looking, F.text)
async def edit_process_looking(message: types.Message, state: FSMContext):
    if message.text.lower() == 'оставить':
        profile = await get_profile_by_tg_id(message.from_user.id)
        await state.update_data(looking=profile['looking'] if profile else '')
    else:
        await state.update_data(looking=message.text.strip())
    
    await message.answer(
        "✅ Принято.\n\n"
        "Отправьте **новое фото** (или напишите 'оставить' чтобы не менять):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(EditForm.photo)

@router.message(EditForm.photo, F.photo)
async def edit_process_photo(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    profile_id = data.get('profile_id')
    profile = await get_profile_by_tg_id(message.from_user.id)
    
    # Удаляем старое фото из S3
    if profile and profile['photo_url']:
        await delete_photo_from_s3(profile['photo_url'])
    
    # Загружаем новое
    photo_id = message.photo[-1].file_id
    try:
        await message.answer("⏳ Загрузка фото...", reply_markup=get_main_menu_inline())
        photo_url = await upload_photo_to_s3(photo_id, bot)
    except Exception as e:
        logger.error(f"Ошибка загрузки в S3: {e}")
        await message.answer("❌ Ошибка загрузки фото.", reply_markup=get_main_menu_inline())
        await state.clear()
        return
    
    await update_profile(profile_id, data['name'], data['occupation'], data['looking'], photo_url)
    await finish_edit(message, bot, profile_id, data, photo_url, state)

@router.message(EditForm.photo, F.text)
async def edit_process_no_photo(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    profile_id = data.get('profile_id')
    profile = await get_profile_by_tg_id(message.from_user.id)
    
    if message.text.lower() == 'оставить' and profile:
        photo_url = profile['photo_url']
    else:
        photo_url = None
        if profile and profile['photo_url']:
            await delete_photo_from_s3(profile['photo_url'])
    
    await update_profile(profile_id, data['name'], data['occupation'], data['looking'], photo_url)
    await finish_edit(message, bot, profile_id, data, photo_url, state)

async def finish_edit(message: types.Message, bot: Bot, profile_id: int, data: dict, photo_url: str, state: FSMContext):
    """Завершение редактирования и отправка на модерацию"""
    
    # Сначала отправляем уведомление админу
    notification_sent = await notify_admin_edit(bot, message.from_user.id, data, photo_url, profile_id)
    
    if notification_sent:
        await message.answer(
            "✅ **Изменения отправлены на модерацию!**\n\n"
            "Ожидайте решения администратора.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline()
        )
        logger.info(f"Profile {profile_id} edit submitted by user {message.from_user.id}")
    else:
        # ❌ Если не удалось отправить — ОТКАТЫВАЕМ изменения!
        await update_profile_status(profile_id, 'approved')
        
        await message.answer(
            "⚠️ **Временная ошибка связи с сервером**\n\n"
            "Изменения не отправлены. Ваша анкета осталась без изменений.\n\n"
            "Попробуйте позже.",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline()
        )
        logger.warning(f"Edit notification failed for profile {profile_id}, changes rolled back")
    
    await state.clear()

@router.callback_query(F.data == "cancel_process")
async def cancel_process(callback: types.CallbackQuery, state: FSMContext, bot: Bot):
    await state.clear()
    has_profile = await user_has_approved_profile(callback.from_user.id)
    await send_main_menu(callback.message, bot)
    await callback.answer()

async def start_form(message: types.Message, state: FSMContext):
    """Начало заполнения анкеты"""
    await message.answer(
        "📝 **Заполнение анкеты**\n\nВведите ваше **Имя**:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ProfileForm.name)
    logger.info(f"Started profile form for user {message.from_user.id}")

@router.message(ProfileForm.name, F.text)
async def process_name(message: types.Message, state: FSMContext):
    if len(message.text.strip()) < 2:
        await message.answer("❌ Имя слишком короткое.", reply_markup=get_cancel_keyboard())
        return
    
    await state.update_data(name=message.text.strip())
    await message.answer("✅ Имя принято.\n\nЧем вы занимаетесь?", reply_markup=get_cancel_keyboard())
    await state.set_state(ProfileForm.occupation)

@router.message(ProfileForm.occupation, F.text)
async def process_occupation(message: types.Message, state: FSMContext):
    if len(message.text.strip()) < 3:
        await message.answer("❌ Описание слишком короткое.", reply_markup=get_cancel_keyboard())
        return
    
    await state.update_data(occupation=message.text.strip())
    await message.answer("✅ Принято.\n\nКого или что вы ищете?", reply_markup=get_cancel_keyboard())
    await state.set_state(ProfileForm.looking)

@router.message(ProfileForm.looking, F.text)
async def process_looking(message: types.Message, state: FSMContext):
    if len(message.text.strip()) < 3:
        await message.answer("❌ Описание слишком короткое.", reply_markup=get_cancel_keyboard())
        return
    
    await state.update_data(looking=message.text.strip())
    await message.answer(
        "✅ Принято.\n\nОтправьте ваше **фото** (или напишите 'нет'):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ProfileForm.photo)

@router.message(ProfileForm.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext, bot: Bot):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    try:
        await message.answer("⏳ Загрузка фото...", reply_markup=get_main_menu_inline())
        photo_url = await upload_photo_to_s3(photo_id, bot)
    except Exception as e:
        logger.error(f"Ошибка загрузки в S3: {e}")
        await message.answer("❌ Ошибка загрузки фото.", reply_markup=get_main_menu_inline())
        await state.clear()
        return
    
    profile_id = await add_profile(
        tg_id=message.from_user.id,
        name=data['name'],
        occupation=data['occupation'],
        looking=data['looking'],
        photo_url=photo_url
    )
    
    await message.answer(
        "✅ **Анкета отправлена на модерацию!**",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    await state.clear()
    await notify_admin(bot, message.from_user.id, data, photo_url, profile_id)
    logger.info(f"Profile {profile_id} submitted by user {message.from_user.id}")

@router.message(ProfileForm.photo, F.text)
async def process_no_photo(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    
    profile_id = await add_profile(
        tg_id=message.from_user.id,
        name=data['name'],
        occupation=data['occupation'],
        looking=data['looking'],
        photo_url=None
    )
    
    await message.answer(
        "✅ **Анкета отправлена на модерацию!**",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    await state.clear()
    await notify_admin(bot, message.from_user.id, data, None, profile_id)
    logger.info(f"Profile {profile_id} submitted by user {message.from_user.id} (no photo)")

async def notify_admin(bot: Bot, user_id: int, data: dict, photo_url: str, profile_id: int) -> bool:
    """Отправить анкету на модерацию в чат. Возвращает True если успешно."""
    text = (
        f"🔔 **Новая анкета на модерацию!**\n\n"
        f"👤 **ID:** {profile_id}\n"
        f"🆔 **Пользователь:** {user_id}\n"
        f"📛 **Имя:** {data['name']}\n"
        f"💼 **Занятие:** {data['occupation']}\n"
        f"🔍 **Ищет:** {data['looking']}\n\n"
        f"⏳ **Статус:** На модерации"
    )
    
    # Пробуем отправить в чат модерации
    try:
        if photo_url:
            await bot.send_photo(
                chat_id=MODERATION_CHAT_ID,
                photo=URLInputFile(photo_url),
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile_id)
            )
        else:
            await bot.send_message(
                chat_id=MODERATION_CHAT_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile_id)
            )
        logger.info(f"Moderation notification sent to chat {MODERATION_CHAT_ID} for profile {profile_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в чат модерации: {e}")
    
    # Фоллбэк: отправляем в ЛС админу
    try:
        if photo_url:
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=URLInputFile(photo_url),
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile_id)
            )
        else:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile_id)
            )
        logger.info(f"Moderation fallback sent to ADMIN_ID {ADMIN_ID} for profile {profile_id}")
        return True
    except Exception as e2:
        logger.error(f"Фоллбэк уведомление тоже не отправлено: {e2}")
        return False

async def notify_admin_edit(bot: Bot, user_id: int, data: dict, photo_url: str, profile_id: int) -> bool:
    """Отправить изменения анкеты на модерацию. Возвращает True если успешно."""
    text = (
        f"✏️ **Изменения анкеты на модерацию!**\n\n"
        f"👤 **ID:** {profile_id}\n"
        f"🆔 **Пользователь:** {user_id}\n"
        f"📛 **Имя:** {data['name']}\n"
        f"💼 **Занятие:** {data['occupation']}\n"
        f"🔍 **Ищет:** {data['looking']}\n\n"
        f"⏳ **Статус:** На модерации"
    )
    
    # Пробуем отправить в чат модерации
    try:
        if photo_url:
            await bot.send_photo(
                chat_id=MODERATION_CHAT_ID,
                photo=URLInputFile(photo_url),
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile_id)
            )
        else:
            await bot.send_message(
                chat_id=MODERATION_CHAT_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile_id)
            )
        logger.info(f"Edit moderation sent to chat {MODERATION_CHAT_ID} for profile {profile_id}")
        return True
    except Exception as e:
        logger.error(f"Ошибка отправки в чат модерации (edit): {e}")
    
    # Фоллбэк: отправляем в ЛС админу
    try:
        if photo_url:
            await bot.send_photo(
                chat_id=ADMIN_ID,
                photo=URLInputFile(photo_url),
                caption=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile_id)
            )
        else:
            await bot.send_message(
                chat_id=ADMIN_ID,
                text=text,
                parse_mode="Markdown",
                reply_markup=get_moderation_keyboard(profile_id)
            )
        logger.info(f"Edit moderation fallback sent to ADMIN_ID {ADMIN_ID} for profile {profile_id}")
        return True
    except Exception as e2:
        logger.error(f"Фоллбэк уведомление (edit) тоже не отправлено: {e2}")
        return False
