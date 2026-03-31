import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "db": os.getenv("DB_NAME"),
    "autocommit": True
}

S3_CONFIG = {
    "endpoint_url": os.getenv("S3_ENDPOINT"),
    "aws_access_key_id": os.getenv("S3_ACCESS_KEY"),
    "aws_secret_access_key": os.getenv("S3_SECRET_KEY"),
    "region_name": os.getenv("S3_REGION", "ru-1")
}
S3_BUCKET = os.getenv("S3_BUCKET")
