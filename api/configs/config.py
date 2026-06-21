import os


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL")
    REDIS_HOST: str = os.getenv("REDIS_HOST", "redis_queue")
    MINIO_ROOT_USER: str = os.getenv("MINIO_ROOT_USER", "minioadmin")
    MINIO_ROOT_PASSWORD: str = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

    BUCKET_NAME: str = "videos-crudos"
    MINIO_ENDPOINT: str = os.getenv("MINIO_ENDPOINT", "almacenamiento-objetos:9000")
    MINIO_PUBLIC_URL: str = os.getenv("MINIO_PUBLIC_URL", "http://localhost:9000")

    LLM_PROVIDER: str = os.getenv(
        "LLM_PROVIDER", "openai"
    )  # "ollama", "openai" o "gemini"

    # Configuracion OLLAMA
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://ollama:11434")
    OLLAMA_TOKEN: str = os.getenv("OLLAMA_TOKEN", "")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

    # Configuracion OpenAI
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # Configuracion Gemini (Google AI Studio)
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


settings = Settings()
