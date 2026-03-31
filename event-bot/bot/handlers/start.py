from aiogram import Router, F, types
from aiogram.filters import CommandStart
from aiogram.types import URLInputFile
from bot.keyboards import get_main_menu, get_refresh_keyboard
from bot.database import get_approved_profiles

router = Router()

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    await message.answer("Привет! Это бот мероприятия. Выберите действие:", reply_markup=get_main_menu())

@router.message(F.text == "👥 Посмотреть участников")
async def view_participants(message: types.Message):
    profiles = await get_approved_profiles()
    if not profiles:
        await message.answer("Пока нет одобренных анкет.")
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
                await message.answer(caption, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка отправки фото: {e}")
            await message.answer(caption, parse_mode="Markdown")
    
    await message.answer("Конец списка.", reply_markup=get_refresh_keyboard())

@router.callback_query(F.data == "refresh_list")
async def refresh_list(callback: types.CallbackQuery):
    await callback.message.delete()
    profiles = await get_approved_profiles()
    if not profiles:
        await callback.message.answer("Пока нет одобренных анкет.")
        return
    
    for profile in profiles:
        caption = f"👤 **{profile['name']}**\n💼 {profile['occupation']}\n🔍 Ищет: {profile['looking']}"
        try:
            if profile['photo_url']:
                await callback.message.answer_photo(
                    photo=URLInputFile(profile['photo_url']),
                    caption=caption,
                    parse_mode="Markdown"
                )
            else:
                await callback.message.answer(caption, parse_mode="Markdown")
        except Exception as e:
            logging.error(f"Ошибка отправки фото: {e}")
            await callback.message.answer(caption, parse_mode="Markdown")
            
    await callback.message.answer("Конец списка.", reply_markup=get_refresh_keyboard())
    await callback.answer()
