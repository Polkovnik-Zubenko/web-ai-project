import logging
import time

from app.celery_app import celery_app
from app.db import SessionLocal
from app.ml.text_model import build_model
from app.models import Analysis

logger = logging.getLogger(__name__)


@celery_app.task(bind=True, name="tickets.process")
def process_ticket(self, payload: dict) -> dict:
    # Асинхронная очередь задач
    started = time.perf_counter()
    self.update_state(state="PROGRESS", meta={"stage": "loading_model", "progress": 20})
    model = build_model()
    model.load()
    self.update_state(state="PROGRESS", meta={"stage": "analyzing_ticket", "progress": 55})
    result = model.generate(payload["text"], payload["creativity"], payload["max_tokens"])
    self.update_state(state="PROGRESS", meta={"stage": "saving_result", "progress": 80})

    with SessionLocal() as db:
        row = Analysis(
            text=payload["text"],
            customer_name=payload.get("customer_name") or "Клиент",
            channel=payload.get("channel") or "web",
            creativity=payload["creativity"],
            max_tokens=payload["max_tokens"],
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
        ticket_id = row.id
        created_at = row.created_at.isoformat()

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info("ticket_task_complete id=%s elapsed_ms=%.2f", ticket_id, elapsed_ms)
    return {
        "stage": "complete",
        "progress": 100,
        "ticket_id": ticket_id,
        "created_at": created_at,
        "sentiment": result.sentiment,
        "category": result.category,
        "urgency": result.urgency,
        "score": result.score,
    }
