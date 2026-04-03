from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_main_menu_inline(has_profile=False):
    """Главное меню - инлайн кнопки"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🪽 Список участников", callback_data="view_participants")
    builder.button(text="📩 Рассказать о себе", callback_data="add_profile")
    
    if has_profile:
        builder.button(text="🗝 Управление анкетой", callback_data="manage_profile")
    
    builder.adjust(1)
    return builder.as_markup()

def get_manage_profile_keyboard():
    """Кнопки управления анкетой"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📝 Редактировать", callback_data="edit_profile")
    builder.button(text="🗑️ Удалить анкету", callback_data="delete_profile")
    builder.button(text="🏠 В главное меню", callback_data="back_to_menu")
    builder.adjust(1)
    return builder.as_markup()

def get_refresh_keyboard():
    """Кнопка обновления списка"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Обновить", callback_data="refresh_list")
    builder.button(text="🏠 В меню", callback_data="back_to_menu")
    builder.adjust(2)
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
    builder.button(text="Отмена", callback_data="cancel_process")
    return builder.as_markup()

def get_back_to_menu_keyboard():
    """Кнопка возврата в меню"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🏠 В главное меню", callback_data="back_to_menu")
    return builder.as_markup()

def get_clear_all_confirm_keyboard():
    """Кнопки подтверждения очистки всех анкет"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Да, удалить все", callback_data="clear_all_confirm")
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

def get_confirm_delete_keyboard():
    """Подтверждение удаления своей анкеты"""
    builder = InlineKeyboardBuilder()
    builder.button(text="⚠️ Да, удалить", callback_data="delete_profile_confirm")
    builder.button(text="❌ Отмена", callback_data="manage_profile")
    builder.adjust(2)
    return builder.as_markup()
