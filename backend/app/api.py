import asyncio
import logging
import time

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Response, WebSocket, WebSocketDisconnect, status
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.auth import authenticate_user, create_access_token, get_current_user, hash_password
from app.db import get_db
from app.errors import ModelUnavailableError
from app.models import Analysis, User
from app.schemas import AnalysisListItem, AnalyzeRequest, AnalyzeResponse, HealthResponse, LoginRequest, RegisterRequest, TaskCreatedResponse, TaskStatusResponse, TicketRequest, TokenResponse, UserResponse
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


@router.post("/auth/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    email = payload.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Пользователь с такой почтой уже существует.")
    user = User(
        email=email,
        hashed_password=hash_password(payload.password),
        name=payload.name,
        role="manager",
        company=payload.company,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user), user=UserResponse.model_validate(user))


@router.post("/auth/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = authenticate_user(db, payload.email.lower(), payload.password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверная почта или пароль.")
    return TokenResponse(access_token=create_access_token(user), user=UserResponse.model_validate(user))


@router.get("/auth/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


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
def create_ticket(payload: TicketRequest, current_user: User = Depends(get_current_user)) -> TaskCreatedResponse:
    task_payload = {**payload.model_dump(), "owner_id": current_user.id}
    task = process_ticket.delay(task_payload)
    return TaskCreatedResponse(
        task_id=task.id,
        status="queued",
        status_url=f"/api/tasks/{task.id}",
        websocket_url=f"/api/tasks/{task.id}/ws",
    )


@router.post("/tickets/sync", response_model=AnalyzeResponse, status_code=status.HTTP_201_CREATED)
def create_ticket_sync(payload: TicketRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> AnalyzeResponse:
    if state.model is None or not state.model.ready:
        raise ModelUnavailableError("ML-модель ещё не готова.")
    result = state.model.generate(payload.text, payload.creativity, payload.max_tokens)
    row = Analysis(
        owner_id=current_user.id,
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
    return _list_analyses(limit, db, None)


@router.get("/tickets", response_model=list[AnalysisListItem])
def list_tickets(limit: int = 50, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> list[AnalysisListItem]:
    owner_id = None if current_user.role == "admin" else current_user.id
    return _list_analyses(limit, db, owner_id)


def _list_analyses(limit: int, db: Session, owner_id: int | None) -> list[AnalysisListItem]:
    limit = max(1, min(limit, 50))
    query = select(Analysis)
    if owner_id is not None:
        query = query.where(Analysis.owner_id == owner_id)
    rows = db.scalars(query.order_by(Analysis.created_at.desc()).limit(limit)).all()
    return [
        AnalysisListItem(
            id=row.id,
            owner_id=row.owner_id,
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
def clear_analyses(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Response:
    query = select(Analysis)
    if current_user.role != "admin":
        query = query.where(Analysis.owner_id == current_user.id)
    for row in db.scalars(query).all():
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
