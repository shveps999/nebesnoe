import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardRemove
from bot.keyboards import get_cancel_keyboard, get_main_menu_reply
from bot.database import add_profile
from bot.config import ADMIN_ID, MODERATION_CHAT_ID
from bot.s3_storage import upload_photo_to_s3
from bot.keyboards import get_moderation_keyboard
from aiogram.types import URLInputFile

logger = logging.getLogger(__name__)
router = Router()

class ProfileForm(StatesGroup):
    name = State()
    occupation = State()
    looking = State()
    photo = State()

@router.callback_query(F.data == "add_profile")
async def add_profile_callback(callback: types.CallbackQuery):
    await callback.message.delete()
    await start_form(callback.message, callback.state)
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
        await message.answer(
            "❌ Имя слишком короткое. Попробуйте еще раз:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(name=message.text.strip())
    await message.answer(
        "✅ Имя принято.\n\nЧем вы занимаетесь? (Работа, учеба, хобби):",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ProfileForm.occupation)

@router.message(ProfileForm.occupation, F.text)
async def process_occupation(message: types.Message, state: FSMContext):
    if len(message.text.strip()) < 3:
        await message.answer(
            "❌ Описание слишком короткое. Попробуйте еще раз:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(occupation=message.text.strip())
    await message.answer(
        "✅ Принято.\n\nКого или что вы ищете на мероприятии?",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ProfileForm.looking)

@router.message(ProfileForm.looking, F.text)
async def process_looking(message: types.Message, state: FSMContext):
    if len(message.text.strip()) < 3:
        await message.answer(
            "❌ Описание слишком короткое. Попробуйте еще раз:",
            reply_markup=get_cancel_keyboard()
        )
        return
    
    await state.update_data(looking=message.text.strip())
    await message.answer(
        "✅ Принято.\n\nОтправьте ваше **фото** (или напишите 'нет', если без фото):",
        parse_mode="Markdown",
        reply_markup=get_cancel_keyboard()
    )
    await state.set_state(ProfileForm.photo)

@router.message(ProfileForm.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext, bot: Bot):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    try:
        await message.answer(
            "⏳ Загрузка фото...",
            reply_markup=get_main_menu_reply()
        )
        photo_url = await upload_photo_to_s3(photo_id, bot)
    except Exception as e:
        logger.error(f"Ошибка загрузки в S3: {e}")
        await message.answer(
            "❌ Ошибка загрузки фото. Попробуйте позже или заполните анкету без фото.",
            reply_markup=get_main_menu_reply()
        )
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
        "✅ **Анкета отправлена на модерацию!**\n\nОжидайте решения администратора.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_reply()
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
        "✅ **Анкета отправлена на модерацию!**\n\nОжидайте решения администратора.",
        parse_mode="Markdown",
        reply_markup=get_main_menu_reply()
    )
    await state.clear()
    
    await notify_admin(bot, message.from_user.id, data, None, profile_id)
    logger.info(f"Profile {profile_id} submitted by user {message.from_user.id} (no photo)")

@router.callback_query(F.data == "cancel_process")
async def cancel_process(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "❌ Заполнение отменено.",
        reply_markup=get_main_menu_reply()
    )
    await callback.answer()
    logger.info(f"User {callback.from_user.id} cancelled profile form")

async def notify_admin(bot: Bot, user_id: int, data: dict, photo_url: str, profile_id: int):
    """Отправить анкету на модерацию в чат"""
    text = (
        f"🔔 **Новая анкета на модерацию!**\n\n"
        f"👤 **ID:** {profile_id}\n"
        f"🆔 **Пользователь:** {user_id}\n"
        f"📛 **Имя:** {data['name']}\n"
        f"💼 **Занятие:** {data['occupation']}\n"
        f"🔍 **Ищет:** {data['looking']}\n\n"
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
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления админу: {e}")
        # Фоллбэк на личный чат админа
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
        except Exception as e2:
            logger.error(f"Фоллбэк уведомление тоже не отправлено: {e2}")
