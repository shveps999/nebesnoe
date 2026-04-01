import aiomysql
from bot.config import DB_CONFIG

async def get_connection():
    return await aiomysql.connect(**DB_CONFIG)

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
                photo_url TEXT,
                status VARCHAR(50) DEFAULT 'pending',
                admin_comment TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
            )
        """)
        await conn.commit()
    conn.close()

async def add_profile(tg_id, name, occupation, looking, photo_url):
    conn = await get_connection()
    async with conn.cursor() as cursor:
        await cursor.execute(
            "INSERT INTO profiles (tg_id, name, occupation, looking, photo_url, status) VALUES (%s, %s, %s, %s, %s, 'pending')",
            (tg_id, name, occupation, looking, photo_url)
        )
        await conn.commit()
        profile_id = cursor.lastrowid
    conn.close()
    return profile_id

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
    """Получить все одобренные профили с фото для удаления"""
    conn = await get_connection()
    async with conn.cursor(aiomysql.DictCursor) as cursor:
        await cursor.execute("SELECT id, photo_url FROM profiles WHERE status = 'approved' AND photo_url IS NOT NULL")
        result = await cursor.fetchall()
    conn.close()
    return result

async def delete_all_approved_profiles():
    """Удалить все одобренные профили из БД"""
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
