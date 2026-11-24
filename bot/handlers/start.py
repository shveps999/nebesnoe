import logging
import re
from aiogram import Router, F, types, Bot
from aiogram.types import URLInputFile
from bot.keyboards import get_main_menu_inline, get_refresh_keyboard, get_consent_keyboard
from bot.database import (
    get_approved_profiles, user_has_approved_profile,
    get_user_last_message, save_user_message,
    get_user_list_messages, save_user_list_messages,
    user_has_consented, save_user_consent
)
from bot.config import ADMIN_ID

logger = logging.getLogger(__name__)
router = Router()

# Ссылка на политику конфиденциальности
PRIVACY_POLICY_URL = "https://docs.google.com/document/d/1bAcr5y_Ne3oFTOYPK8TXbOe09e-ZyMJhHrb8fpMug0M/edit?usp=sharing"


def display_portfolio_url(url: str) -> str:
    """Убирает http:// и https:// для показа. В БД ссылка остаётся полной."""
    if not url:
        return ""
    return re.sub(r'^https?://', '', url.strip(), flags=re.IGNORECASE)


async def delete_message_safe(bot: Bot, chat_id: int, message_id: int):
    """Безопасное удаление сообщения (игнорирует ошибки)"""
    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug(f"Deleted message {message_id} in chat {chat_id}")
    except Exception as e:
        logger.debug(f"Could not delete message {message_id}: {e}")

async def _delete_participant_list(bot: Bot, user_tg_id: int):
    """Удалить список участников по сохранённым ID сообщений.

    Удаляются ровно те сообщения, которые были отправлены при показе списка —
    без "веера" по ID.
    """
    message_ids = await get_user_list_messages(user_tg_id)
    if message_ids:
        for message_id in message_ids:
            await delete_message_safe(bot, user_tg_id, message_id)
        await save_user_list_messages(user_tg_id, [])
        logger.debug(f"Deleted participant list ({len(message_ids)} messages) for user {user_tg_id}")
        return

    # --- Совместимость со старым форматом (якорь "-" + веер на 30 сообщений) ---
    # Срабатывает только для списков, отправленных ДО обновления бота.
    # Через пару недель после деплоя этот блок можно удалить.
    saved_id = await get_user_last_message(user_tg_id)
    if saved_id and saved_id < 0:
        anchor_id = abs(saved_id)
        for offset in range(0, 30):
            await delete_message_safe(bot, user_tg_id, anchor_id - offset)
        await save_user_message(user_tg_id, None)
        logger.debug(f"Deleted legacy participant list for user {user_tg_id}")

async def show_consent_flow(message: types.Message, bot: Bot):
    """Показать поток согласия на обработку данных"""
    tg_id = message.from_user.id

    # 1. Приветственное сообщение
    await message.answer(
        "Привет! Рады видеть тебя в нашем боте, сейчас все покажем ✨"
    )

    # 2. Сообщение с согласием (без превью ссылки)
    consent_text = (
        "Перед тем, как начать, нам нужно получить твое согласие на обработку персональных данных:\n\n"
        "🔹 Собираем: имя, сферу деятельности, кого ищете, фото, никнейм в тг, ссылку на работы (по желанию)\n"
        "🔹 Удалить анкету: через меню «Управление анкетой» → «Удалить анкету»\n"
        "🔹 Перед каждым новым ивентом — удаляется автоматически\n\n"
        f"Нажимая «Я согласен», вы принимаете условия Политики обработки персональных данных."
    )

    consent_msg = await message.answer(
        consent_text,
        parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=get_consent_keyboard()
    )

    # Сохраняем ID сообщения согласия для последующего удаления (отрицательное = согласие)
    await save_user_message(tg_id, -consent_msg.message_id)
    logger.info(f"Shown consent flow to user {tg_id}")

async def send_main_menu(message: types.Message, bot: Bot, user_tg_id: int, delete_old: bool = True):
    """Отправить главное меню, удалив предыдущее меню и список участников"""
    has_profile = await user_has_approved_profile(user_tg_id)

    if delete_old:
        # Если был открыт список участников (например, пользователь нажал /start) — чистим и его
        await _delete_participant_list(bot, user_tg_id)
        last_menu_id = await get_user_last_message(user_tg_id)
        if last_menu_id and last_menu_id > 0:
            await delete_message_safe(bot, user_tg_id, last_menu_id)

    new_message = await message.answer(
        "🏠 **Главное меню**\n\nВыберите действие:",
        parse_mode="Markdown",
        reply_markup=get_main_menu_inline(has_profile)
    )

    await save_user_message(user_tg_id, new_message.message_id)
    logger.info(f"Sent main menu to user {user_tg_id}, message_id={new_message.message_id}")
    return new_message

async def send_participants_list(message: types.Message, bot: Bot, user_tg_id: int):
    """Отправить список участников.

    Кнопки "Обновить / В меню" вешаются на ПОСЛЕДНЮЮ карточку списка.
    ID всех отправленных сообщений сохраняются в БД (JSON), чтобы при
    обновлении/выходе удалить ровно их — без точки-заглушки и без веера.
    Админ-панель под списком НЕ показывается: админ-инструменты —
    команды /clear_all и /broadcast, модерация — в чате модерации.
    """
    # Если список уже был показан — сначала убираем его (например, при "Обновить")
    await _delete_participant_list(bot, user_tg_id)

    # Удаляем предыдущее меню
    last_menu_id = await get_user_last_message(user_tg_id)
    if last_menu_id and last_menu_id > 0:
        await delete_message_safe(bot, user_tg_id, last_menu_id)

    if user_tg_id != ADMIN_ID:
        has_profile = await user_has_approved_profile(user_tg_id)
        if not has_profile:
            info_msg = await message.answer(
                "Чтобы посмотреть список участников, "
                "сначала добавьте **свою анкету**.\n\n",
                parse_mode="Markdown",
                reply_markup=get_main_menu_inline()
            )
            await save_user_message(user_tg_id, info_msg.message_id)
            logger.info(f"User {user_tg_id} tried to view participants without profile")
            return

    profiles = await get_approved_profiles()

    if not profiles:
        empty_msg = await message.answer(
            "Список пока пуст.\n\nБудь первым!",
            reply_markup=get_main_menu_inline()
        )
        await save_user_message(user_tg_id, empty_msg.message_id)
        return

    sent_ids = []          # ID всех сообщений списка — для точного удаления
    keyboard_sent = False  # удалось ли повесить кнопки на последнюю карточку
    total = len(profiles)

    for index, profile in enumerate(profiles):
        is_last = (index == total - 1)
        # Кнопки — только на последней карточке
        markup = get_refresh_keyboard() if is_last else None

        # ПРОСТОЙ ТЕКСТ БЕЗ MARKDOWN — никаких ошибок парсинга
        tg_line = f"\n\n🔗 Тг: {profile.get('tg_username')}" if profile.get('tg_username') else ""

        # Ссылка на работы: показываем без https:// (в БД она полная)
        works_short = display_portfolio_url(profile.get('portfolio_url'))
        works_line = f"\n\n🎨 Работы: {works_short}" if works_short else ""

        caption = (
            f"{profile['name']}\n\n"
            f"🪄 {profile['occupation'] or ''}\n\n"
            f"💡 Ищу: {profile['looking'] or ''}"
            f"{tg_line}"
            f"{works_line}"
        )

        sent_msg = None
        try:
            if profile['photo_url']:
                sent_msg = await message.answer_photo(
                    photo=URLInputFile(profile['photo_url']),
                    caption=caption,
                    parse_mode=None,
                    reply_markup=markup
                )
            else:
                sent_msg = await message.answer(
                    caption,
                    parse_mode=None,
                    disable_web_page_preview=True,
                    reply_markup=markup
                )
        except Exception as e:
            logger.error(f"Ошибка отправки анкеты {profile['id']}: {e}")
            # Фоллбэк: отправляем анкету текстом (с кнопками, если это последняя)
            try:
                sent_msg = await message.answer(
                    caption,
                    parse_mode=None,
                    disable_web_page_preview=True,
                    reply_markup=markup
                )
            except Exception as e2:
                logger.error(f"Не удалось отправить анкету {profile['id']} даже текстом: {e2}")

        if sent_msg is not None:
            sent_ids.append(sent_msg.message_id)
            if is_last:
                keyboard_sent = True

    # Страховка: если последняя карточка не отправилась вообще —
    # кнопки не теряются, а появляются на отдельном сообщении со счётчиком
    if not keyboard_sent:
        tail_msg = await message.answer(
            f"👥 Участников: {total}",
            reply_markup=get_refresh_keyboard()
        )
        sent_ids.append(tail_msg.message_id)

    # Сохраняем точные ID всех сообщений списка и очищаем якорь меню
    await save_user_list_messages(user_tg_id, sent_ids)
    await save_user_message(user_tg_id, None)

    logger.info(f"Sent {len(profiles)} profiles to user {user_tg_id}")

@router.callback_query(F.data == "view_participants")
async def view_participants_callback(callback: types.CallbackQuery, bot: Bot):
    """Показать список участников (удаляет меню)"""
    user_tg_id = callback.from_user.id

    if not await user_has_consented(user_tg_id):
        await callback.answer("⚠️ Сначала дайте согласие на обработку данных", show_alert=True)
        return

    # Отвечаем сразу, чтобы не ловить "query is too old" на длинных списках
    await callback.answer()

    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    await send_participants_list(callback.message, bot, user_tg_id)

@router.callback_query(F.data == "refresh_list")
async def refresh_list_callback(callback: types.CallbackQuery, bot: Bot):
    """Обновить список (удаляет старый список перед показом нового)"""
    user_tg_id = callback.from_user.id

    if not await user_has_consented(user_tg_id):
        await callback.answer("⚠️ Сначала дайте согласие на обработку данных", show_alert=True)
        return

    await callback.answer("Список обновлён! 🔄")

    # Сообщение с кнопками (последняя карточка) удаляем сразу,
    # остальные сообщения старого списка удалит send_participants_list
    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    await send_participants_list(callback.message, bot, user_tg_id)

@router.callback_query(F.data == "back_to_menu")
async def back_to_menu_callback(callback: types.CallbackQuery, bot: Bot):
    """Вернуться в меню (удаляет список анкет и показывает чистое меню)"""
    user_tg_id = callback.from_user.id

    if not await user_has_consented(user_tg_id):
        await callback.answer("⚠️ Сначала дайте согласие на обработку данных", show_alert=True)
        return

    await callback.answer()

    await _delete_participant_list(bot, user_tg_id)

    saved_id = await get_user_last_message(user_tg_id)
    if saved_id and saved_id > 0:
        await delete_message_safe(bot, user_tg_id, saved_id)

    await delete_message_safe(bot, user_tg_id, callback.message.message_id)
    await send_main_menu(callback.message, bot, user_tg_id, delete_old=False)

@router.callback_query(F.data == "consent_agree")
async def consent_agree_callback(callback: types.CallbackQuery, bot: Bot):
    """Обработка согласия на обработку данных"""
    user_tg_id = callback.from_user.id

    await save_user_consent(user_tg_id)

    # Удаляем сообщения согласия
    saved_id = await get_user_last_message(user_tg_id)
    if saved_id and saved_id < 0:
        consent_msg_id = abs(saved_id)
        await delete_message_safe(bot, user_tg_id, consent_msg_id)
        await delete_message_safe(bot, user_tg_id, consent_msg_id - 1)

    # Показываем главное меню
    await send_main_menu(callback.message, bot, user_tg_id, delete_old=False)
    await callback.answer()
    logger.info(f"User {user_tg_id} gave consent to data processing")
