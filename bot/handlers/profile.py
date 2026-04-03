import logging
import re
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from bot.keyboards import get_cancel_keyboard, get_main_menu_inline, get_manage_profile_keyboard, get_confirm_delete_keyboard
from bot.database import add_profile, update_profile, user_has_approved_profile, get_profile_by_tg_id, delete_profile_by_tg_id, update_profile_status
from bot.config import ADMIN_ID, MODERATION_CHAT_ID
from bot.s3_storage import upload_photo_to_s3, delete_photo_from_s3
from bot.keyboards import get_moderation_keyboard
from aiogram.types import URLInputFile

logger = logging.getLogger(__name__)
router = Router()

class ProfileForm(StatesGroup):
    name = State()
    occupation = State()
    looking = State()
    tg_username = State()  # ← НОВОЕ: Telegram username
    photo = State()

class EditForm(StatesGroup):
    profile_id = State()
    name = State()
    occupation = State()
    looking = State()
    tg_username = State()  # ← НОВОЕ
    photo = State()

async def delete_message_safe(bot: Bot, chat_id: int, message_id: int):
    """Безопасное удаление сообщения"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except:
        pass

def validate_tg_username(text: str) -> bool:
    """Проверяет что username начинается с @ и содержит только допустимые символы"""
    text = text.strip()
    if text.lower() == 'skip' or text == '/skip':
        return True  # Пропуск разрешён
    if not text.startswith('@'):
        return False
    # Проверяем формат: @username (3-32 символа, буквы, цифры, подчёркивания)
    pattern = r'^@[a-zA-Z0-9_]{3,32}$'
    return bool(re.match(pattern, text))

def format_tg_username(text: str) -> str:
    """Добавляет @ если нет"""
    text = text.strip()
    if text.lower() == 'skip' or text == '/skip':
        return None
    if not text.startswith('@'):
        return '@' + text
    return text

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
    
    await delete_message_safe(callback.bot, callback.from_user.id, callback.message.message_id)
    await start_form(callback.message, state, callback.bot)
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
    
    await delete_message_safe(callback.bot, callback.from_user.id, callback.message.message_id)
    await callback.message.answer(
        "⚙️ **Управление анкетой**\n\nВыбери действие:",
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
    await delete_message_safe(callback.bot, callback.from_user.id, callback.message.message_id)
    msg = await callback.message.answer(
        f"📝 **Редактирование анкеты**\n\n"
        f"Текущее имя: {profile['name']}\n\n"
        f"Введи **новое имя** (или напиши «оставить» чтобы не менять):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
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
    
    await delete_message_safe(callback.bot, callback.from_user.id, callback.message.message_id)
    await callback.message.answer(
        "⚠️ **Удаление анкеты**\n\n"
        "Уверен, что хочешь удалить свою визитку?\n\n",
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
    
    if profile['photo_url']:
        await delete_photo_from_s3(profile['photo_url'])
    
    deleted_count, _ = await delete_profile_by_tg_id(callback.from_user.id)
    
    await delete_message_safe(bot, callback.from_user.id, callback.message.message_id)
    await callback.message.answer(
        "**Визитка успешно удалена**\n\n",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    
    logger.info(f"User {callback.from_user.id} deleted their profile")
    await callback.answer()

@router.message(EditForm.name, F.text)
async def edit_process_name(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    if message.text.lower() == 'оставить':
        profile = await get_profile_by_tg_id(message.from_user.id)
        await state.update_data(name=profile['name'] if profile else '')
    else:
        await state.update_data(name=message.text.strip())
    
    msg = await message.answer(
        "✍️ Имя принято.\n\n"
        "Твое направление деятельности? (или напиши «оставить» чтобы не менять):",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(EditForm.occupation)

@router.message(EditForm.occupation, F.text)
async def edit_process_occupation(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    if message.text.lower() == 'оставить':
        profile = await get_profile_by_tg_id(message.from_user.id)
        await state.update_data(occupation=profile['occupation'] if profile else '')
    else:
        await state.update_data(occupation=message.text.strip())
    
    msg = await message.answer(
        "💌 Принято.\n\n"
        "Кого или что вы ищешь? (или напиши «оставить» чтобы не менять):",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(EditForm.looking)

@router.message(EditForm.looking, F.text)
async def edit_process_looking(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    if message.text.lower() == 'оставить':
        profile = await get_profile_by_tg_id(message.from_user.id)
        await state.update_data(looking=profile['looking'] if profile else '')
    else:
        await state.update_data(looking=message.text.strip())
    
    msg = await message.answer(
        "👀 Принято.\n\n"
        "🔗 **Твой Telegram для связи**\n\n"
        "Введи свой никнейм в формате **@username**, если хочешь, чтобы тебе могли написать.\n\n"
        "Или нажми **/skip** чтобы пропустить:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(EditForm.tg_username)

@router.message(EditForm.tg_username, F.text)
async def edit_process_tg_username(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    text = message.text.strip()
    
    # Проверяем на пропуск
    if text.lower() == 'skip' or text == '/skip':
        tg_username = None
        msg = await message.answer(
            "🕯 Пропущено.\n\n"
            "📸 **Теперь отправь свое фото, чтобы тебя могли узнать на ивенте**\n\n",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard()
        )
        await state.update_data(last_message_id=msg.message_id)
        await state.update_data(tg_username=None)
        await state.set_state(EditForm.photo)
        return
    
    # Проверяем формат
    if not validate_tg_username(text):
        msg = await message.answer(
            "❌ **Неверный формат Telegram username**\n\n"
            "Никнейм должен:\n"
            "• Начинаться с **@**\n"
            "• Содержать 3-32 символа\n"
            "• Содержать только буквы, цифры и _\n\n"
            "Пример: **@username**\n\n"
            "Попробуй еще раз или напиши **/skip**:",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard()
        )
        await state.update_data(last_message_id=msg.message_id)
        return
    
    tg_username = format_tg_username(text)
    await state.update_data(tg_username=tg_username)
    
    msg = await message.answer(
        f"💫 Принято: **{tg_username}**\n\n"
        "📸 **Теперь отправь свое фото, чтобы тебя могли узнать на ивенте**\n\n",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(EditForm.photo)

@router.message(EditForm.photo, F.photo)
async def edit_process_photo(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    profile_id = data.get('profile_id')
    profile = await get_profile_by_tg_id(message.from_user.id)
    
    if profile and profile['photo_url']:
        await delete_photo_from_s3(profile['photo_url'])
    
    photo_id = message.photo[-1].file_id
    try:
        photo_url = await upload_photo_to_s3(photo_id, bot)
    except Exception as e:
        logger.error(f"Ошибка загрузки в S3: {e}")
        msg = await message.answer("❌ Ошибка загрузки фото. Попробуй еще раз.", reply_markup=get_cancel_keyboard())
        await state.update_data(last_message_id=msg.message_id)
        return
    
    await update_profile(profile_id, data['name'], data['occupation'], data['looking'], data.get('tg_username'), photo_url)
    await finish_edit(message, bot, profile_id, data, photo_url, state)

@router.message(EditForm.photo, ~F.photo)
async def edit_process_photo_not_photo(message: types.Message, state: FSMContext, bot: Bot):
    """Если прислали не фото — показываем ошибку"""
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    msg = await message.answer(
        "📸 Пожалуйста, прикрепи изображение.\n",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)

async def finish_edit(message: types.Message, bot: Bot, profile_id: int, data: dict, photo_url: str, state: FSMContext):
    """Завершение редактирования и отправка на модерацию"""
    notification_sent = await notify_admin_edit(bot, message.from_user.id, data, photo_url, profile_id)
    
    if notification_sent:
        await message.answer(
            "**☑️ Мы получили все данные и скоро опубликуем их в общем списке гостей**\n\n",
            parse_mode="Markdown",
            reply_markup=get_main_menu_inline()
        )
        logger.info(f"Profile {profile_id} edit submitted by user {message.from_user.id}")
    else:
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
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, callback.from_user.id, last_msg_id)
    
    await state.clear()
    has_profile = await user_has_approved_profile(callback.from_user.id)
    await callback.message.answer(
        "❌ Отменено.",
        reply_markup=get_main_menu_inline(has_profile)
    )
    await callback.answer()

async def start_form(message: types.Message, state: FSMContext, bot: Bot):
    """Начало заполнения анкеты"""
    msg = await message.answer(
        "📩 **Заполнение анкеты**\n\nВведи **Имя**:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(ProfileForm.name)
    logger.info(f"Started profile form for user {message.from_user.id}")

@router.message(ProfileForm.name, F.text)
async def process_name(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    if len(message.text.strip()) < 2:
        msg = await message.answer("❌ Имя слишком короткое.", reply_markup=get_cancel_keyboard())
        await state.update_data(last_message_id=msg.message_id)
        return
    
    await state.update_data(name=message.text.strip())
    msg = await message.answer("✍️ Имя принято.\n\nКакое у тебя направление деятельности?", reply_markup=get_cancel_keyboard())
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(ProfileForm.occupation)

@router.message(ProfileForm.occupation, F.text)
async def process_occupation(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    if len(message.text.strip()) < 3:
        msg = await message.answer("❌ Описание слишком короткое.", reply_markup=get_cancel_keyboard())
        await state.update_data(last_message_id=msg.message_id)
        return
    
    await state.update_data(occupation=message.text.strip())
    msg = await message.answer("✨ Записали.\n\nКого или что ищешь?", reply_markup=get_cancel_keyboard())
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(ProfileForm.looking)

@router.message(ProfileForm.looking, F.text)
async def process_looking(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    if len(message.text.strip()) < 3:
        msg = await message.answer("❌ Описание слишком короткое.", reply_markup=get_cancel_keyboard())
        await state.update_data(last_message_id=msg.message_id)
        return
    
    await state.update_data(looking=message.text.strip())
    msg = await message.answer(
        "💌 Принято.\n\n"
        "📱 **Твой Telegram для связи**\n\n"
        "Введи никнейм в формате **@username**, если хочешь, чтобы тебе могли написать\n\n"
        "💡 Или нажми **/skip** чтобы пропустить:",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(ProfileForm.tg_username)

@router.message(ProfileForm.tg_username, F.text)
async def process_tg_username(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    text = message.text.strip()
    
    # Проверяем на пропуск
    if text.lower() == 'skip' or text == '/skip':
        tg_username = None
        msg = await message.answer(
            "🚨 Пропущено.\n\n"
            "📸 **Теперь отправь свое фото, чтобы тебя могли узнать на ивенте**\n\n",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard()
        )
        await state.update_data(last_message_id=msg.message_id)
        await state.update_data(tg_username=None)
        await state.set_state(ProfileForm.photo)
        return
    
    # Проверяем формат
    if not validate_tg_username(text):
        msg = await message.answer(
            "❌ **Неверный формат Telegram username**\n\n"
            "Никнейм должен:\n"
            "• Начинаться с **@**\n"
            "• Содержать 3-32 символа\n"
            "• Содержать только буквы, цифры и _\n\n"
            "Пример: **@username**\n\n"
            "Попробуйте еще раз или напишите **/skip**:",
            parse_mode="Markdown",
            reply_markup=get_cancel_keyboard()
        )
        await state.update_data(last_message_id=msg.message_id)
        return
    
    tg_username = format_tg_username(text)
    await state.update_data(tg_username=tg_username)
    
    msg = await message.answer(
        f"⚡️ Принято: **{tg_username}**\n\n"
        "📸 **Теперь отправь свое фото, чтобы тебя могли узнать на ивенте**\n\n",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(ProfileForm.photo)

@router.message(ProfileForm.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    photo_id = message.photo[-1].file_id
    try:
        photo_url = await upload_photo_to_s3(photo_id, bot)
    except Exception as e:
        logger.error(f"Ошибка загрузки в S3: {e}")
        msg = await message.answer("❌ Ошибка загрузки фото. Попробуйте еще раз.", reply_markup=get_cancel_keyboard())
        await state.update_data(last_message_id=msg.message_id)
        return
    
    profile_id = await add_profile(
        tg_id=message.from_user.id,
        name=data['name'],
        occupation=data['occupation'],
        looking=data['looking'],
        tg_username=data.get('tg_username'),
        photo_url=photo_url
    )
    
    await message.answer(
        "**Мы получили все данные и скоро опубликуем анкету в общем списке**",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline()
    )
    await state.clear()
    await notify_admin(bot, message.from_user.id, data, photo_url, profile_id)
    logger.info(f"Profile {profile_id} submitted by user {message.from_user.id}")

@router.message(ProfileForm.photo, ~F.photo)
async def process_photo_not_photo(message: types.Message, state: FSMContext, bot: Bot):
    """Если прислали не фото — показываем ошибку"""
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await delete_message_safe(bot, message.from_user.id, last_msg_id)
    
    msg = await message.answer(
        "❌ **Нужно отправить фото!**\n\n"
        "📸 Пожалуйста, прикрепите изображение.\n",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)

async def notify_admin(bot: Bot, user_id: int, data: dict, photo_url: str, profile_id: int) -> bool:
    """Отправить анкету на модерацию в чат. Возвращает True если успешно."""
    tg_username = data.get('tg_username')
    tg_line = f"\n🔗 Тг: {tg_username}" if tg_username else ""
    
    text = (
        f"🔔 **Новая анкета на модерацию!**\n\n"
        f"👤 **ID:** {profile_id}\n"
        f"🆔 **Пользователь:** {user_id}\n"
        f"📛 **Имя:** {data['name']}\n"
        f"💼 **Занятие:** {data['occupation']}\n"
        f"🔍 **Ищет:** {data['looking']}"
        f"{tg_line}\n\n"
        f"⏳ **Статус:** На модерации"
    )
    
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
    tg_username = data.get('tg_username')
    tg_line = f"\n🔗 Тг: {tg_username}" if tg_username else ""
    
    text = (
        f"✏️ **Изменения анкеты на модерацию!**\n\n"
        f"👤 **ID:** {profile_id}\n"
        f"🆔 **Пользователь:** {user_id}\n"
        f"📛 **Имя:** {data['name']}\n"
        f"💼 **Занятие:** {data['occupation']}\n"
        f"🔍 **Ищет:** {data['looking']}"
        f"{tg_line}\n\n"
        f"⏳ **Статус:** На модерации"
    )
    
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
