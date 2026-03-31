from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

def get_main_menu():
    builder = ReplyKeyboardBuilder()
    builder.button(text="👥 Посмотреть участников")
    builder.button(text="📝 Добавить анкету")
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True)

def get_refresh_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить список", callback_data="refresh_list")
    return builder.as_markup()

def get_moderation_keyboard(profile_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"admin_approve_{profile_id}")
    builder.button(text="✏️ Запросить изменения", callback_data=f"admin_edit_{profile_id}")
    return builder.as_markup()

def get_cancel_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_process")
    return builder.as_markup()
