import json
import aiomysql
from bot.config import DB_CONFIG

async def get_connection():
    return await aiomysql.connect(**DB_CONFIG)

async def _ensure_user_messages_table(cursor):
    """Создать таблицу user_messages, если её нет"""
    await cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_messages (
            tg_id BIGINT PRIMARY KEY,
            last_menu_message_id INT NULL,
            list_message_ids TEXT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
        )
    """)

async def init_consents_table():
    """Создать таблицу согласий если нет"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_consents (
                tg_id BIGINT PRIMARY KEY,
                consented BOOLEAN DEFAULT FALSE,
                consented_at TIMESTAMP NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        await conn.commit()
    conn.close()

async def init_db():
    """Создание таблиц при запуске"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tg_id BIGINT NOT NULL,
                name VARCHAR(255) NOT NULL,
                occupation TEXT,
                looking TEXT,
                tg_username VARCHAR(100),
                portfolio_url TEXT,
                photo_url TEXT,
                photo_file_id TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                admin_comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)

        # Добавляем колонку tg_username если её нет
        try:
            await cursor.execute("ALTER TABLE profiles ADD COLUMN tg_username VARCHAR(100) AFTER looking")
        except:
            pass  # Колонка уже существует

        # Добавляем колонку portfolio_url если её нет
        try:
            await cursor.execute("ALTER TABLE profiles ADD COLUMN portfolio_url TEXT AFTER tg_username")
        except:
            pass  # Колонка уже существует

        # Добавляем колонку photo_file_id если её нет (кэш фото Telegram)
        try:
            await cursor.execute("ALTER TABLE profiles ADD COLUMN photo_file_id TEXT AFTER photo_url")
        except:
            pass  # Колонка уже существует

        # Таблица служебных сообщений (меню / список участников)
        await _ensure_user_messages_table(cursor)

        # Миграция: колонка со списком ID сообщений списка участников (JSON)
        try:
            await cursor.execute("ALTER TABLE user_messages ADD COLUMN list_message_ids TEXT NULL AFTER last_menu_message_id")
        except:
            pass  # Колонка уже существует

        await conn.commit()
    conn.close()

    # Инициализировать таблицу согласий
    await init_consents_table()

async def add_profile(tg_id, name, occupation, looking, tg_username, photo_url, portfolio_url=None, photo_file_id=None):
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("DELETE FROM profiles WHERE tg_id = %s", (tg_id,))
        await cursor.execute(
            "INSERT INTO profiles (tg_id, name, occupation, looking, tg_username, portfolio_url, photo_url, photo_file_id, status) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending')",
            (tg_id, name, occupation, looking, tg_username, portfolio_url, photo_url, photo_file_id)
        )
        await conn.commit()
        profile_id = cursor.lastrowid
    conn.close()
    return profile_id

async def update_profile(profile_id, name, occupation, looking, tg_username, photo_url, portfolio_url=None, photo_file_id=None):
    """Обновить анкету. photo_file_id ВСЕГДА перезаписывается переданным значением:
    при смене фото старый кэш должен сброситься (None), иначе список покажет старое фото."""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute(
            "UPDATE profiles SET name = %s, occupation = %s, looking = %s, tg_username = %s, "
            "portfolio_url = %s, photo_url = %s, photo_file_id = %s, status = 'pending' WHERE id = %s",
            (name, occupation, looking, tg_username, portfolio_url, photo_url, photo_file_id, profile_id)
        )
        await conn.commit()
    conn.close()

async def update_photo_file_id(profile_id, file_id):
    """Сохранить кэш file_id фото (после первой отправки через URL)"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute(
            "UPDATE profiles SET photo_file_id = %s WHERE id = %s",
            (file_id, profile_id)
        )
        await conn.commit()
    conn.close()

async def update_profile_photo(profile_id, photo_url, photo_file_id=None):
    """Админ-замена фото (/setphoto): обновляет ТОЛЬКО фото и его кэш.
    Статус и остальные поля не трогает — повторная модерация не нужна."""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute(
            "UPDATE profiles SET photo_url = %s, photo_file_id = %s WHERE id = %s",
            (photo_url, photo_file_id, profile_id)
        )
        await conn.commit()
    conn.close()

async def get_all_profiles():
    """Все анкеты кратко (для админ-команды /profiles)"""
    conn = await get_connection()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT id, name, tg_username, status FROM profiles ORDER BY id DESC")
        result = await cursor.fetchall()
    conn.close()
    return result

async def get_bot_stats():
    """Сводная статистика для админ-команды /stats"""
    conn = await get_connection()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        # Все пользователи бота = все, кто дал согласие
        await cursor.execute(
            "SELECT COUNT(*) AS cnt FROM user_consents WHERE consented = TRUE"
        )
        users_total = (await cursor.fetchone())['cnt']

        await cursor.execute(
            "SELECT COUNT(*) AS cnt FROM user_consents "
            "WHERE consented = TRUE AND consented_at >= NOW() - INTERVAL 7 DAY"
        )
        users_new_7d = (await cursor.fetchone())['cnt']

        await cursor.execute("SELECT COUNT(DISTINCT tg_id) AS cnt FROM profiles")
        users_with_profile = (await cursor.fetchone())['cnt']

        await cursor.execute("SELECT COUNT(*) AS cnt FROM profiles WHERE status = 'approved'")
        approved = (await cursor.fetchone())['cnt']

        await cursor.execute("SELECT COUNT(*) AS cnt FROM profiles WHERE status = 'pending'")
        pending = (await cursor.fetchone())['cnt']

        # Аудитория рассылки «всем» = то же, что вернёт get_all_user_tg_ids()
        await cursor.execute(
            "SELECT COUNT(*) AS cnt FROM ("
            "SELECT tg_id FROM profiles "
            "UNION "
            "SELECT tg_id FROM user_consents WHERE consented = TRUE"
            ") AS recipients"
        )
        broadcast_all = (await cursor.fetchone())['cnt']

        await cursor.execute(
            "SELECT COUNT(DISTINCT tg_id) AS cnt FROM profiles WHERE status = 'approved'"
        )
        broadcast_approved = (await cursor.fetchone())['cnt']
    conn.close()
    return {
        'users_total': users_total,
        'users_new_7d': users_new_7d,
        'users_with_profile': users_with_profile,
        'users_without_profile': max(0, users_total - users_with_profile),
        'approved': approved,
        'pending': pending,
        'broadcast_all': broadcast_all,
        'broadcast_approved': broadcast_approved,
    }

async def delete_profile_by_tg_id(tg_id):
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT photo_url FROM profiles WHERE tg_id = %s AND status = 'approved'", (tg_id,))
        result = await cursor.fetchone()
        photo_url = result[0] if result else None

        await cursor.execute("DELETE FROM profiles WHERE tg_id = %s", (tg_id,))
        deleted_count = cursor.rowcount
        await conn.commit()
    conn.close()
    return deleted_count, photo_url

async def get_pending_profiles():
    conn = await get_connection()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM profiles WHERE status = 'pending' ORDER BY id DESC")
        result = await cursor.fetchall()
    conn.close()
    return result

async def get_approved_profiles():
    conn = await get_connection()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM profiles WHERE status = 'approved' ORDER BY id DESC")
        result = await cursor.fetchall()
    conn.close()
    return result

async def get_all_approved_with_photos():
    conn = await get_connection()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT id, photo_url FROM profiles WHERE status = 'approved' AND photo_url IS NOT NULL")
        result = await cursor.fetchall()
    conn.close()
    return result

async def delete_all_approved_profiles():
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("DELETE FROM profiles WHERE status = 'approved'")
        deleted_count = cursor.rowcount
        await conn.commit()
    conn.close()
    return deleted_count

async def update_profile_status(profile_id, status, comment=None):
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute(
            "UPDATE profiles SET status = %s, admin_comment = %s WHERE id = %s",
            (status, comment, profile_id)
        )
        await conn.commit()
    conn.close()

async def get_profile_by_id(profile_id):
    conn = await get_connection()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM profiles WHERE id = %s", (profile_id,))
        result = await cursor.fetchone()
    conn.close()
    return result

async def get_profile_by_tg_id(tg_id):
    conn = await get_connection()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT * FROM profiles WHERE tg_id = %s ORDER BY id DESC LIMIT 1", (tg_id,))
        result = await cursor.fetchone()
    conn.close()
    return result

async def user_has_approved_profile(tg_id):
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute(
            "SELECT COUNT(*) FROM profiles WHERE tg_id = %s AND status = 'approved'",
            (tg_id,)
        )
        result = await cursor.fetchone()
    conn.close()
    return result[0] > 0 if result else False

async def save_user_message(tg_id: int, message_id):
    """Сохранить ID служебного сообщения пользователя.

    Знак кодирует тип сообщения:
      > 0  — главное меню (или сервисное сообщение с кнопками меню)
      < 0  — экран согласия на обработку данных
      None — очистить

    ID сообщений списка участников хранятся отдельно, см. save_user_list_messages.
    """
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await _ensure_user_messages_table(cursor)
        await cursor.execute(
            "INSERT INTO user_messages (tg_id, last_menu_message_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE last_menu_message_id = %s",
            (tg_id, message_id, message_id)
        )
        await conn.commit()
    conn.close()

async def get_user_last_message(tg_id: int):
    """Получить ID служебного сообщения (меню > 0, согласие < 0, None — нет)"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await _ensure_user_messages_table(cursor)
        await cursor.execute("SELECT last_menu_message_id FROM user_messages WHERE tg_id = %s", (tg_id,))
        result = await cursor.fetchone()
    conn.close()
    return result[0] if result else None

async def save_user_list_messages(tg_id: int, message_ids):
    """Сохранить ID ВСЕХ сообщений списка участников (карточки + сообщение с кнопками).

    Хранится как JSON-массив в колонке list_message_ids.
    Пустой список очищает запись.
    """
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await _ensure_user_messages_table(cursor)
        payload = json.dumps(list(message_ids)) if message_ids else None
        await cursor.execute(
            "INSERT INTO user_messages (tg_id, list_message_ids) VALUES (%s, %s) ON DUPLICATE KEY UPDATE list_message_ids = %s",
            (tg_id, payload, payload)
        )
        await conn.commit()
    conn.close()

async def get_user_list_messages(tg_id: int):
    """Получить список ID сообщений списка участников (пустой список, если нет)"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await _ensure_user_messages_table(cursor)
        await cursor.execute("SELECT list_message_ids FROM user_messages WHERE tg_id = %s", (tg_id,))
        result = await cursor.fetchone()
    conn.close()
    if not result or not result[0]:
        return []
    try:
        ids = json.loads(result[0])
        return [int(m) for m in ids] if isinstance(ids, list) else []
    except (ValueError, TypeError):
        return []

async def get_all_user_tg_ids():
    """Все получатели рассылки «всем»:
    создатели анкет + все, кто дал согласие (даже если анкеты нет).
    UNION сам убирает дубли."""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute(
            "SELECT tg_id FROM profiles "
            "UNION "
            "SELECT tg_id FROM user_consents WHERE consented = TRUE"
        )
        result = await cursor.fetchall()
    conn.close()
    return [row[0] for row in result]

async def get_approved_user_tg_ids():
    """Получить список Telegram ID пользователей с одобренными анкетами"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT DISTINCT tg_id FROM profiles WHERE status = 'approved'")
        result = await cursor.fetchall()
    conn.close()
    return [row[0] for row in result]

async def user_has_consented(tg_id: int) -> bool:
    """Проверить, дал ли пользователь согласие"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT consented FROM user_consents WHERE tg_id = %s", (tg_id,))
        result = await cursor.fetchone()
    conn.close()
    return result[0] if result else False

async def save_user_consent(tg_id: int):
    """Сохранить согласие пользователя"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("""
            INSERT INTO user_consents (tg_id, consented, consented_at)
            VALUES (%s, TRUE, NOW())
            ON DUPLICATE KEY UPDATE consented = TRUE, consented_at = NOW()
        """, (tg_id,))
        await conn.commit()
    conn.close()
