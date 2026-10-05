import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.session import AsyncSessionLocal, create_db_and_tables, get_async_db
from app.services.recommender.predict import load_model_and_mappings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # app Startup
    logger.info("Application startup...")
    logger.info(f"Keras backend configured as: {settings.KERAS_BACKEND}")

    logger.info("Initializing database and creating tables if they don't exist...")

    await create_db_and_tables()
    logger.info("Database tables checked/created.")

    logger.info("Attempting to preload recommendation model and mappings...")
    try:
        # Need a db session to load mappings
        async with AsyncSessionLocal() as db:
            await load_model_and_mappings(db)
        logger.info("Recommendation model and mappings preloading attempted.")
    except Exception as e:
        logger.error(f"Error during startup model preloading: {e}", exc_info=True)

    yield
    # Shutdown
    logger.info("Application shutdown...")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan,
)

# CORS middleware configuration
cors_origins_list = [
    origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()
]
if not cors_origins_list:
    cors_origins_list = ["http://localhost:5173", "http://127.0.0.1:5173"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Root endpoint
@app.get("/", tags=["Root"])
async def read_root():
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} v{settings.PROJECT_VERSION}"
    }


# Include API routers
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_async_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        logger.error(f"Health check failed: DB connection error - {e}")
        raise HTTPException(status_code=503, detail="Database connection error")

