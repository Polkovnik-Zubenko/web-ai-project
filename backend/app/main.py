import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from redis import Redis
from sqlalchemy import select

from app.api import router
from app.config import settings
from app.db import SessionLocal, engine
from app.errors import register_error_handlers
from app.logging_config import configure_logging
from app.ml.text_model import build_model
from app.seed import seed_demo_data
from app.state import state

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Управление жизненным циклом контекстных переменных
    logger.info("startup_begin app=%s env=%s", settings.app_name, settings.environment)
    state.model = build_model()
    state.model.load()
    state.redis = Redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=2)
    with SessionLocal() as db:
        db.execute(select(1))
        seed_demo_data(db)
    logger.info("startup_complete")
    try:
        yield
    finally:
        # Graceful Shutdown
        logger.info("shutdown_begin")
        if state.redis is not None:
            state.redis.close()
        engine.dispose()
        logger.info("shutdown_complete")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="AI text insight service with FastAPI, SQLAlchemy, Redis health checks and Streamlit UI.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)
register_error_handlers(app)
app.include_router(router)
Instrumentator().instrument(app).expose(app, endpoint="/api/metrics")
