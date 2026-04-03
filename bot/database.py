import aiomysql
from bot.config import DB_CONFIG

async def get_connection():
    return await aiomysql.connect(**DB_CONFIG)

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
                photo_url TEXT,
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
        
        await conn.commit()
    conn.close()
    
    # Инициализировать таблицу согласий
    await init_consents_table()

async def add_profile(tg_id, name, occupation, looking, tg_username, photo_url):
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("DELETE FROM profiles WHERE tg_id = %s", (tg_id,))
        await cursor.execute(
            "INSERT INTO profiles (tg_id, name, occupation, looking, tg_username, photo_url, status) VALUES (%s, %s, %s, %s, %s, %s, 'pending')",
            (tg_id, name, occupation, looking, tg_username, photo_url)
        )
        await conn.commit()
        profile_id = cursor.lastrowid
    conn.close()
    return profile_id

async def update_profile(profile_id, name, occupation, looking, tg_username, photo_url):
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute(
            "UPDATE profiles SET name = %s, occupation = %s, looking = %s, tg_username = %s, photo_url = %s, status = 'pending' WHERE id = %s",
            (name, occupation, looking, tg_username, photo_url, profile_id)
        )
        await conn.commit()
    conn.close()

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

async def save_user_message(tg_id: int, message_id: int):
    """Сохранить ID последнего сообщения меню пользователя"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                tg_id BIGINT PRIMARY KEY,
                last_menu_message_id INT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        await cursor.execute(
            "INSERT INTO user_messages (tg_id, last_menu_message_id) VALUES (%s, %s) ON DUPLICATE KEY UPDATE last_menu_message_id = %s",
            (tg_id, message_id, message_id)
        )
        await conn.commit()
    conn.close()

async def get_user_last_message(tg_id: int) -> int:
    """Получить ID последнего сообщения меню пользователя"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                tg_id BIGINT PRIMARY KEY,
                last_menu_message_id INT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        await cursor.execute("SELECT last_menu_message_id FROM user_messages WHERE tg_id = %s", (tg_id,))
        result = await cursor.fetchone()
    conn.close()
    return result[0] if result else None

async def get_all_user_tg_ids():
    """Получить список всех уникальных Telegram ID пользователей"""
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute("SELECT DISTINCT tg_id FROM profiles")
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
