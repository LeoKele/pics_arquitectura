import os


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis_queue")
    MINIO_ROOT_USER: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    MINIO_ROOT_PASSWORD: str = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://ollama:11434")
    BUCKET_NAME: str = "videos-crudos"


settings = Settings()
