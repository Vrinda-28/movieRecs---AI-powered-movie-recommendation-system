import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from the project root if it exists
env_path = Path(".") / ".env"
load_dotenv(dotenv_path=env_path)


class Settings:
    PROJECT_NAME: str = "RecommendationApp"
    PROJECT_VERSION: str = "1.0.0"

    # Database settings
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "admin")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "admin1234")
    POSTGRES_SERVER: str = os.getenv("POSTGRES_SERVER", "db")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "recommenderdb")
    
    _raw_db_url = os.getenv("DATABASE_URL", "")
    if _raw_db_url and "${" not in _raw_db_url:
        DATABASE_URL: str = _raw_db_url
    else:
        DATABASE_URL: str = f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"


    # Redis and Celery settings
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    CELERY_BROKER_URL: str = os.getenv(
        "CELERY_BROKER_URL", f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
    )
    CELERY_RESULT_BACKEND: str = os.getenv(
        "CELERY_RESULT_BACKEND", f"redis://{REDIS_HOST}:{REDIS_PORT}/0"
    )
    CELERY_TIMEZONE: str = os.getenv("CELERY_TIMEZONE", "Asia/Kolkata")

    # FastAPI security & CORS settings
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY", "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    )
    ALGORITHM: str = os.getenv("ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 120))
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000"
    )

    # Recommender settings
    MAX_CONTEXT_LENGTH: int = int(os.getenv("MAX_CONTEXT_LENGTH", 10))
    MIN_SEQUENCE_LENGTH: int = int(os.getenv("MIN_SEQUENCE_LENGTH", 3))
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", 32))
    RETRIEVAL_K: int = int(os.getenv("RETRIEVAL_K", 50))
    MODEL_PATH: str = os.getenv("MODEL_PATH", "./models_store/gru4rec_model.keras")

    # Set Keras backend (tensorflow, jax, torch)
    # This needs to be set before Keras is imported for the first time.
    KERAS_BACKEND: str = os.getenv("KERAS_BACKEND", "tensorflow")
    os.environ["KERAS_BACKEND"] = KERAS_BACKEND

    # Ensure models_store directory exists
    Path("./models_store").mkdir(parents=True, exist_ok=True)
    Path("./data").mkdir(
        parents=True, exist_ok=True
    )  # For Movielens data if downloaded


settings = Settings()

if settings.KERAS_BACKEND:
    print(f"Keras backend set to: {settings.KERAS_BACKEND}")
else:
    print(
        "Warning: KERAS_BACKEND environment variable not found. Keras will use its default backend."
    )
