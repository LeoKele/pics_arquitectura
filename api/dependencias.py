import boto3
import redis
from configs.config import settings
from minio import Minio

r = redis.Redis(host=settings.REDIS_HOST, port=6379, decode_responses=True)

minio_client = Minio(
    settings.MINIO_ENDPOINT,
    access_key=settings.MINIO_ROOT_USER,
    secret_key=settings.MINIO_ROOT_PASSWORD,
    secure=False,
)

s3_internal_client = boto3.client(
    "s3",
    endpoint_url=f"http://{settings.MINIO_ENDPOINT}",
    aws_access_key_id=settings.MINIO_ROOT_USER,
    aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
    config=boto3.session.Config(signature_version="s3v4"),
)

s3_public_client = boto3.client(
    "s3",
    endpoint_url=settings.MINIO_PUBLIC_URL,
    aws_access_key_id=settings.MINIO_ROOT_USER,
    aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
    config=boto3.session.Config(signature_version="s3v4"),
)
