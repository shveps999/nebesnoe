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
