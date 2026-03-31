import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from bot.keyboards import get_cancel_keyboard
from bot.database import add_profile
from bot.config import ADMIN_ID
from bot.s3_storage import upload_photo_to_s3
from aiogram.types import URLInputFile

router = Router()

class ProfileForm(StatesGroup):
    name = State()
    occupation = State()
    looking = State()
    photo = State()

@router.message(F.text == "📝 Добавить анкету")
async def start_form(message: types.Message, state: FSMContext):
    await message.answer("Введите ваше **Имя**:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
    await state.set_state(ProfileForm.name)

@router.message(ProfileForm.name, F.text)
async def process_name(message: types.Message, state: FSMContext):
    if len(message.text) < 2:
        await message.answer("Имя слишком короткое. Попробуйте еще раз:")
        return
    await state.update_data(name=message.text)
    await message.answer("Чем вы занимаетесь? (Работа, учеба, хобби):", reply_markup=get_cancel_keyboard())
    await state.set_state(ProfileForm.occupation)

@router.message(ProfileForm.occupation, F.text)
async def process_occupation(message: types.Message, state: FSMContext):
    await state.update_data(occupation=message.text)
    await message.answer("Кого или что вы ищете на мероприятии?", reply_markup=get_cancel_keyboard())
    await state.set_state(ProfileForm.looking)

@router.message(ProfileForm.looking, F.text)
async def process_looking(message: types.Message, state: FSMContext):
    await state.update_data(looking=message.text)
    await message.answer("Отправьте ваше фото (или напишите 'нет', если без фото):", reply_markup=get_cancel_keyboard())
    await state.set_state(ProfileForm.photo)

@router.message(ProfileForm.photo, F.photo)
async def process_photo(message: types.Message, state: FSMContext, bot: Bot):
    photo_id = message.photo[-1].file_id
    data = await state.get_data()
    
    try:
        await message.answer("⏳ Загрузка фото...")
        photo_url = await upload_photo_to_s3(photo_id, bot)
    except Exception as e:
        logging.error(f"Ошибка загрузки в S3: {e}")
        await message.answer("Ошибка загрузки фото. Попробуйте позже.")
        await state.clear()
        return

    await add_profile(
        tg_id=message.from_user.id,
        name=data['name'],
        occupation=data['occupation'],
        looking=data['looking'],
        photo_url=photo_url
    )
    await message.answer("Анкета отправлена на модерацию! Ожидайте решения админа.")
    await state.clear()
    await notify_admin(bot, message.from_user.id, data, photo_url)

@router.message(ProfileForm.photo, F.text)
async def process_no_photo(message: types.Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    await add_profile(
        tg_id=message.from_user.id,
        name=data['name'],
        occupation=data['occupation'],
        looking=data['looking'],
        photo_url=None
    )
    await message.answer("Анкета отправлена на модерацию! Ожидайте решения админа.")
    await state.clear()
    await notify_admin(bot, message.from_user.id, data, None)

@router.callback_query(F.data == "cancel_process")
async def cancel_process(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("Заполнение отменено.")
    await callback.answer()

async def notify_admin(bot: Bot, user_id, data, photo_url):
    try:
        text = f"🔔 **Новая анкета!**\nID: {user_id}\nИмя: {data['name']}\nЗанятие: {data['occupation']}\nИщет: {data['looking']}"
        if photo_url:
            await bot.send_photo(
                ADMIN_ID,
                photo=URLInputFile(photo_url),
                caption=text,
                parse_mode="Markdown"
            )
        else:
            await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"Ошибка уведомления админа: {e}")
