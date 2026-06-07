import logging
import time

from fastapi import APIRouter, Depends, Response, status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.errors import ModelUnavailableError
from app.models import Analysis
from app.schemas import AnalysisListItem, AnalyzeRequest, AnalyzeResponse, HealthResponse
from app.state import state

router = APIRouter(prefix="/api", tags=["text-analysis"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    # Health Checks
    database_status = "ok"
    redis_status = "ok"
    model_status = "ready" if state.model and state.model.ready else "error"

    try:
        db.execute(select(1))
    except Exception:
        logger.exception("database_health_failed")
        database_status = "error"

    try:
        if state.redis is None:
            raise RedisError("redis is not initialized")
        state.redis.ping()
    except RedisError:
        logger.exception("redis_health_failed")
        redis_status = "error"

    status_value = "ok" if database_status == redis_status == "ok" and model_status == "ready" else "degraded"
    return HealthResponse(status=status_value, database=database_status, redis=redis_status, model=model_status)


@router.post("/analyze", response_model=AnalyzeResponse, status_code=status.HTTP_201_CREATED)
def analyze(payload: AnalyzeRequest, db: Session = Depends(get_db)) -> AnalyzeResponse:
    if state.model is None or not state.model.ready:
        raise ModelUnavailableError("ML-модель ещё не готова.")

    started = time.perf_counter()
    result = state.model.generate(payload.text, payload.creativity, payload.max_tokens)
    row = Analysis(
        text=payload.text,
        creativity=payload.creativity,
        max_tokens=payload.max_tokens,
        sentiment=result.sentiment,
        score=result.score,
        summary=result.summary,
        metrics={**result.metrics, "recommendations": result.recommendations},
    )
    # ORM
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("analysis_saved id=%s elapsed_ms=%.2f", row.id, (time.perf_counter() - started) * 1000)

    return AnalyzeResponse(
        id=row.id,
        sentiment=row.sentiment,
        score=row.score,
        summary=row.summary,
        recommendations=result.recommendations,
        metrics=result.metrics,
        created_at=row.created_at,
    )


@router.get("/analyses", response_model=list[AnalysisListItem])
def list_analyses(limit: int = 10, db: Session = Depends(get_db)) -> list[AnalysisListItem]:
    limit = max(1, min(limit, 50))
    rows = db.scalars(select(Analysis).order_by(Analysis.created_at.desc()).limit(limit)).all()
    return [
        AnalysisListItem(
            id=row.id,
            sentiment=row.sentiment,
            score=row.score,
            summary=row.summary,
            metrics=row.metrics,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.delete("/analyses", status_code=status.HTTP_204_NO_CONTENT)
def clear_analyses(db: Session = Depends(get_db)) -> Response:
    for row in db.scalars(select(Analysis)).all():
        db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
