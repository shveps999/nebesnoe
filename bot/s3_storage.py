import io
import aioboto3
from bot.config import S3_CONFIG, S3_BUCKET
import uuid
import logging

logger = logging.getLogger(__name__)
session = aioboto3.Session()

async def upload_photo_to_s3(file_id: str, bot) -> str:
    """
    Скачивает фото от пользователя и загружает в S3.
    Возвращает публичную ссылку.
    """
    try:
        # 1. Получаем файл от Telegram
        file = await bot.get_file(file_id)
        file_path = file.file_path
        
        # 2. Скачиваем в память
        destination = io.BytesIO()
        await bot.download_file(file_path, destination)
        destination.seek(0)
        
        # 3. Генерируем уникальное имя
        file_name = f"profiles/{uuid.uuid4()}.jpg"
        
        # 4. Загружаем в S3
        async with session.client("s3", **S3_CONFIG) as s3:
            await s3.put_object(
                Bucket=S3_BUCKET,
                Key=file_name,
                Body=destination,
                ContentType="image/jpeg",
                ACL="public-read"
            )
        
        # 5. Формируем ссылку
        public_url = f"{S3_CONFIG['endpoint_url']}/{S3_BUCKET}/{file_name}"
        logger.info(f"Фото загружено в S3: {public_url}")
        return public_url
    
    except Exception as e:
        logger.error(f"Ошибка загрузки в S3: {e}")
        raise

async def delete_photo_from_s3(photo_url: str) -> bool:
    """
    Удаляет фото из S3 по URL.
    Возвращает True если успешно, False если ошибка.
    """
    try:
        # Извлекаем ключ из URL (например: profiles/uuid.jpg)
        # URL формат: https://s3.timeweb.com/bucket_name/profiles/uuid.jpg
        parts = photo_url.split('/')
        if len(parts) < 2:
            logger.error(f"Некорректный URL: {photo_url}")
            return False
        
        # Ключ это всё после имени бакета
        bucket_index = parts.index(S3_BUCKET) if S3_BUCKET in parts else -1
        if bucket_index == -1:
            logger.error(f"Бакет не найден в URL: {photo_url}")
            return False
        
        key = '/'.join(parts[bucket_index + 1:])
        
        # Удаляем из S3
        async with session.client("s3", **S3_CONFIG) as s3:
            await s3.delete_object(Bucket=S3_BUCKET, Key=key)
        
        logger.info(f"Фото удалено из S3: {key}")
        return True
    
    except Exception as e:
        logger.error(f"Ошибка удаления из S3: {e}")
        return False

async def delete_multiple_photos_from_s3(photo_urls: list) -> dict:
    """
    Удаляет несколько фото из S3.
    Возвращает статистику: {'success': N, 'failed': N}
    """
    stats = {'success': 0, 'failed': 0}
    
    for photo_url in photo_urls:
        if photo_url:
            result = await delete_photo_from_s3(photo_url)
            if result:
                stats['success'] += 1
            else:
                stats['failed'] += 1
    
    return stats
