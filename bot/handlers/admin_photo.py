import logging
from aiogram import Router, F, types, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command
from bot.config import ADMIN_ID
from bot.database import (
    get_profile_by_id, get_all_profiles, update_profile_photo,
    user_has_approved_profile
)
from bot.s3_storage import upload_photo_to_s3, delete_photo_from_s3
from bot.keyboards import get_cancel_keyboard, get_main_menu_inline

logger = logging.getLogger(__name__)
router = Router()


class AdminPhotoForm(StatesGroup):
    photo = State()


async def _delete_safe(bot: Bot, chat_id: int, message_id: int):
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


@router.message(Command("profiles"), F.from_user.id == ADMIN_ID)
async def cmd_profiles(message: types.Message):
    """Список всех анкет с ID — чтобы знать, кому менять фото"""
    profiles = await get_all_profiles()
    if not profiles:
        await message.answer("Анкет пока нет.", parse_mode=None)
        return

    lines = ["📋 Анкеты: статус · ID · имя · ник"]
    for p in profiles:
        status = "✅" if p['status'] == 'approved' else ("⏳" if p['status'] == 'pending' else "❓")
        username = p.get('tg_username') or "—"
        lines.append(f"{status} #{p['id']} · {p['name']} · {username}")

    # Кусками по ~3500 символов, чтобы не упереться в лимит Telegram (4096)
    chunk = []
    size = 0
    for line in lines:
        if chunk and size + len(line) + 1 > 3500:
            await message.answer("\n".join(chunk), parse_mode=None)
            chunk, size = [], 0
        chunk.append(line)
        size += len(line) + 1
    if chunk:
        await message.answer("\n".join(chunk), parse_mode=None)


@router.message(Command("setphoto"), F.from_user.id == ADMIN_ID)
async def cmd_setphoto(message: types.Message, state: FSMContext):
    """Админ-замена фото анкеты: /setphoto <id>"""
    parts = (message.text or "").split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer(
            "Использование: /setphoto <ID анкеты>\n\n"
            "ID можно посмотреть командой /profiles",
            parse_mode=None
        )
        return

    profile_id = int(parts[1])
    profile = await get_profile_by_id(profile_id)
    if not profile:
        await message.answer(f"❌ Анкета #{profile_id} не найдена. Список: /profiles", parse_mode=None)
        return

    await state.update_data(
        setphoto_profile_id=profile_id,
        setphoto_old_url=profile.get('photo_url')
    )
    msg = await message.answer(
        f"📸 Пришли новое фото для анкеты #{profile_id} ({profile['name']}).\n\n"
        f"Статус анкеты не изменится, модерация не нужна.",
        parse_mode=None,
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state(AdminPhotoForm.photo)
    logger.info(f"Admin {message.from_user.id} started setphoto for profile {profile_id}")


@router.message(AdminPhotoForm.photo, F.photo)
async def admin_setphoto_photo(message: types.Message, state: FSMContext, bot: Bot):
    """Получили фото: S3 -> БД (без смены статуса) -> удаление старого фото"""
    data = await state.get_data()
    profile_id = data.get('setphoto_profile_id')
    old_url = data.get('setphoto_old_url')
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await _delete_safe(bot, message.from_user.id, last_msg_id)

    # Анкету могли удалить, пока админ искал фото — перепроверяем
    profile = await get_profile_by_id(profile_id) if profile_id else None
    if not profile:
        await state.clear()
        await message.answer(
            "❌ Анкета больше не существует.",
            parse_mode=None,
            reply_markup=get_main_menu_inline()
        )
        return

    photo_id = message.photo[-1].file_id
    try:
        photo_url = await upload_photo_to_s3(photo_id, bot)
    except Exception as e:
        logger.error(f"setphoto: ошибка загрузки в S3: {e}")
        msg = await message.answer(
            "❌ Ошибка загрузки фото. Пришли ещё раз.",
            parse_mode=None,
            reply_markup=get_cancel_keyboard()
        )
        await state.update_data(last_message_id=msg.message_id)
        return

    # Только фото + кэш. Статус, тексты, портфолио — не трогаем.
    await update_profile_photo(profile_id, photo_url, photo_file_id=photo_id)

    # Старое фото удаляем ПОСЛЕ успешного обновления, чтобы не потерять его при сбое
    if old_url and old_url != photo_url:
        try:
            await delete_photo_from_s3(old_url)
        except Exception as e:
            logger.warning(f"setphoto: старое фото не удалено из S3: {e}")

    await state.clear()

    has_profile = await user_has_approved_profile(message.from_user.id)
    await message.answer_photo(
        photo=photo_id,
        caption=(
            f"✅ Фото анкеты #{profile_id} ({profile['name']}) обновлено.\n"
            f"Статус: {profile['status']} (без изменений).\n"
            f"В списке участников покажется при следующем обновлении."
        ),
        parse_mode=None,
        reply_markup=get_main_menu_inline(has_profile)
    )
    logger.info(f"Admin {message.from_user.id} replaced photo of profile {profile_id}")


@router.message(AdminPhotoForm.photo, Command("cancel"))
async def admin_setphoto_cancel_cmd(message: types.Message, state: FSMContext, bot: Bot):
    """Отмена командой /cancel"""
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await _delete_safe(bot, message.from_user.id, last_msg_id)
    await state.clear()
    await message.answer("❌ Отменено.", parse_mode=None, reply_markup=get_main_menu_inline())


@router.message(AdminPhotoForm.photo)
async def admin_setphoto_not_photo(message: types.Message, state: FSMContext, bot: Bot):
    """Прислали не фото — переспрашиваем"""
    data = await state.get_data()
    last_msg_id = data.get('last_message_id')
    if last_msg_id:
        await _delete_safe(bot, message.from_user.id, last_msg_id)
    msg = await message.answer(
        "📸 Нужно именно фото. Пришли изображение или нажми «Отмена» (/cancel).",
        parse_mode=None,
        reply_markup=get_cancel_keyboard()
    )
    await state.update_data(last_message_id=msg.message_id)
