import asyncio
import logging
import time

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect, status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.db import get_db
from app.errors import ModelUnavailableError
from app.models import Analysis
from app.schemas import AnalysisListItem, AnalyzeRequest, AnalyzeResponse, HealthResponse, TaskCreatedResponse, TaskStatusResponse, TicketRequest
from app.state import state
from app.tasks import process_ticket

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
        customer_name="Клиент",
        channel="web",
        creativity=payload.creativity,
        max_tokens=payload.max_tokens,
        sentiment=result.sentiment,
        score=result.score,
        category=result.category,
        urgency=result.urgency,
        summary=result.summary,
        suggested_reply=result.suggested_reply,
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
        category=row.category,
        urgency=row.urgency,
        score=row.score,
        summary=row.summary,
        suggested_reply=row.suggested_reply,
        recommendations=result.recommendations,
        metrics=result.metrics,
        created_at=row.created_at,
    )


@router.post("/tickets", response_model=TaskCreatedResponse, status_code=status.HTTP_202_ACCEPTED)
def create_ticket(payload: TicketRequest) -> TaskCreatedResponse:
    task = process_ticket.delay(payload.model_dump())
    return TaskCreatedResponse(
        task_id=task.id,
        status="queued",
        status_url=f"/api/tasks/{task.id}",
        websocket_url=f"/api/tasks/{task.id}/ws",
    )


@router.post("/tickets/sync", response_model=AnalyzeResponse, status_code=status.HTTP_201_CREATED)
def create_ticket_sync(payload: TicketRequest, db: Session = Depends(get_db)) -> AnalyzeResponse:
    if state.model is None or not state.model.ready:
        raise ModelUnavailableError("ML-модель ещё не готова.")
    result = state.model.generate(payload.text, payload.creativity, payload.max_tokens)
    row = Analysis(
        text=payload.text,
        customer_name=payload.customer_name,
        channel=payload.channel,
        creativity=payload.creativity,
        max_tokens=payload.max_tokens,
        sentiment=result.sentiment,
        score=result.score,
        category=result.category,
        urgency=result.urgency,
        summary=result.summary,
        suggested_reply=result.suggested_reply,
        metrics={**result.metrics, "recommendations": result.recommendations},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str) -> TaskStatusResponse:
    # Брокер и Backend
    task = AsyncResult(task_id, app=celery_app)
    return _task_status(task_id, task)


@router.websocket("/tasks/{task_id}/ws")
async def task_status_ws(websocket: WebSocket, task_id: str) -> None:
    # реализована проверка статуса задачи посредством WebSocket
    await websocket.accept()
    try:
        while True:
            task = AsyncResult(task_id, app=celery_app)
            status_payload = _task_status(task_id, task).model_dump()
            await websocket.send_json(status_payload)
            if task.state in {"SUCCESS", "FAILURE", "REVOKED"}:
                break
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        logger.info("task_ws_disconnect task_id=%s", task_id)


@router.get("/analyses", response_model=list[AnalysisListItem])
def list_analyses(limit: int = 10, db: Session = Depends(get_db)) -> list[AnalysisListItem]:
    limit = max(1, min(limit, 50))
    rows = db.scalars(select(Analysis).order_by(Analysis.created_at.desc()).limit(limit)).all()
    return [
        AnalysisListItem(
            id=row.id,
            customer_name=row.customer_name,
            channel=row.channel,
            sentiment=row.sentiment,
            category=row.category,
            urgency=row.urgency,
            score=row.score,
            summary=row.summary,
            suggested_reply=row.suggested_reply,
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


def _to_response(row: Analysis) -> AnalyzeResponse:
    return AnalyzeResponse(
        id=row.id,
        sentiment=row.sentiment,
        category=row.category,
        urgency=row.urgency,
        score=row.score,
        summary=row.summary,
        suggested_reply=row.suggested_reply,
        recommendations=row.metrics.get("recommendations", []),
        metrics=row.metrics,
        created_at=row.created_at,
    )


def _task_status(task_id: str, task: AsyncResult) -> TaskStatusResponse:
    info = task.info if isinstance(task.info, dict) else {}
    progress = int(info.get("progress", 100 if task.successful() else 0))
    stage = str(info.get("stage", task.state.lower()))
    return TaskStatusResponse(
        task_id=task_id,
        state=task.state,
        progress=progress,
        stage=stage,
        ticket_id=info.get("ticket_id"),
        result=task.result if task.successful() and isinstance(task.result, dict) else None,
    )
