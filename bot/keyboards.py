from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu_inline():
    """Главное меню - инлайн кнопки (всегда под сообщением)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="👥 Посмотреть участников", callback_data="view_participants")
    builder.button(text="📝 Добавить анкету", callback_data="add_profile")
    builder.adjust(1)
    return builder.as_markup()

def get_refresh_keyboard():
    """Кнопка обновления списка"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить список", callback_data="refresh_list")
    return builder.as_markup()

def get_moderation_keyboard(profile_id):
    """Кнопки модерации для админа"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Одобрить", callback_data=f"admin_approve_{profile_id}")
    builder.button(text="✏️ Запросить изменения", callback_data=f"admin_edit_{profile_id}")
    builder.adjust(2)
    return builder.as_markup()

def get_cancel_keyboard():
    """Кнопка отмены заполнения анкеты"""
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Отмена", callback_data="cancel_process")
    return builder.as_markup()

def get_back_to_menu_keyboard():
    """Кнопка возврата в меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 В главное меню", callback_data="back_to_menu")
    return builder.as_markup()

def get_clear_all_confirm_keyboard():
    """Кнопки подтверждения очистки всех анкет"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ ДА, УДАЛИТЬ ВСЁ", callback_data="clear_all_confirm")
    builder.button(text="❌ Отмена", callback_data="clear_all_cancel")
    builder.adjust(2)
    return builder.as_markup()

def get_admin_keyboard():
    """Админ-панель с кнопками управления"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🗑️ Удалить все анкеты", callback_data="clear_all")
    builder.button(text="📊 Статистика", callback_data="admin_stats")
    builder.adjust(2)
    return builder.as_markup()
