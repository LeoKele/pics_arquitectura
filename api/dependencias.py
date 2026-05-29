import boto3
import redis
from botocore.client import Config
from configs.config import settings
from minio import Minio

# Cliente de Redis
r = redis.Redis(host=settings.REDIS_HOST, port=6379, decode_responses=True)

# Cliente de MinIO (Librería Minio oficial)
minio_client = Minio(
    "almacenamiento-objetos:9000",
    access_key=settings.MINIO_ROOT_USER,
    secret_key=settings.MINIO_ROOT_PASSWORD,
    secure=False,
)

# Cliente de S3 (boto3) compatible con MinIO para Multipart Upload
s3_client = boto3.client(
    "s3",
    endpoint_url="http://almacenamiento-objetos:9000",
    aws_access_key_id=settings.MINIO_ROOT_USER,
    aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)

# Cliente de S3 (boto3) con la URL pública/externa de MinIO para la generación de Presigned URLs
s3_public_client = boto3.client(
    "s3",
    endpoint_url=settings.MINIO_PUBLIC_URL,
    aws_access_key_id=settings.MINIO_ROOT_USER,
    aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
    config=Config(signature_version="s3v4"),
    region_name="us-east-1",
)
