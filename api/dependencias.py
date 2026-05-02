import redis
from configs.config import settings
from minio import Minio

# Cliente de Redis
r = redis.Redis(host=settings.REDIS_HOST, port=6379, decode_responses=True)

# Cliente de MinIO
minio_client = Minio(
    "almacenamiento-objetos:9000",
    access_key=settings.MINIO_ROOT_USER,
    secret_key=settings.MINIO_ROOT_PASSWORD,
    secure=False,
)
