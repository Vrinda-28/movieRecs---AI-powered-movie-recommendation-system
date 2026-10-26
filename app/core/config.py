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
        DATABASE_URL: str = (
            f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}:{POSTGRES_PORT}/{POSTGRES_DB}"
        )

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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
        os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 120)
    )
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000",
    )

    # Recommender settings
    MAX_CONTEXT_LENGTH: int = int(os.getenv("MAX_CONTEXT_LENGTH", 10))
    MIN_SEQUENCE_LENGTH: int = int(os.getenv("MIN_SEQUENCE_LENGTH", 3))
    EMBEDDING_DIM: int = int(os.getenv("EMBEDDING_DIM", 32))
    GRU_UNITS: int = int(os.getenv("GRU_UNITS", 32))
    RETRIEVAL_K: int = int(os.getenv("RETRIEVAL_K", 50))
    MODEL_PATH: str = os.getenv("MODEL_PATH", "./models_store/gru4rec_model.keras")

    # Training hyperparameters
    EPOCHS: int = int(os.getenv("EPOCHS", 10))
    BATCH_SIZE: int = int(os.getenv("BATCH_SIZE", 256))
    LEARNING_RATE: float = float(os.getenv("LEARNING_RATE", 0.005))
    VALIDATION_SPLIT: float = float(os.getenv("VALIDATION_SPLIT", 0.1))
    EARLY_STOPPING_PATIENCE: int = int(os.getenv("EARLY_STOPPING_PATIENCE", 3))
    MASK_ZERO: bool = os.getenv("MASK_ZERO", "True").lower() in ("true", "1", "yes")
    PADDING_MODE: str = os.getenv("PADDING_MODE", "right")  # "right" or "left"

    # Explanation and Diversity Settings
    SIMILARITY_EXPLANATION_THRESHOLD: float = float(
        os.getenv("SIMILARITY_EXPLANATION_THRESHOLD", "0.40")
    )
    ENABLE_MMR_RERANKING: bool = os.getenv("ENABLE_MMR_RERANKING", "False").lower() in (
        "true",
        "1",
        "yes",
    )
    MMR_LAMBDA: float = float(os.getenv("MMR_LAMBDA", "0.7"))

    # Groq AI settings
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    GROQ_MODEL: str = os.getenv(
        "GROQ_MODEL", os.getenv("GEMINI_MODEL", "llama-3.3-70b-versatile")
    )
    GROQ_TIMEOUT_SECONDS: float = float(
        os.getenv("GROQ_TIMEOUT_SECONDS", os.getenv("GEMINI_TIMEOUT_SECONDS", "20.0"))
    )
    AI_RATE_LIMIT_PER_MIN: int = int(os.getenv("AI_RATE_LIMIT_PER_MIN", "10"))
    ASK_ALLOW_MODEL_KNOWLEDGE: bool = os.getenv(
        "ASK_ALLOW_MODEL_KNOWLEDGE", "False"
    ).lower() in ("true", "1", "yes")

    # Compatibility aliases
    @property
    def GEMINI_API_KEY(self) -> str:
        return self.GROQ_API_KEY

    @property
    def GEMINI_MODEL(self) -> str:
        return self.GROQ_MODEL

    @property
    def ai_enabled(self) -> bool:
        return bool(self.GROQ_API_KEY)

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
