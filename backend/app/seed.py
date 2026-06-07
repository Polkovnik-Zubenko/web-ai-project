from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import Analysis, User


def seed_demo_data(db: Session) -> None:
    try:
        _seed_demo_data(db)
        db.commit()
    except IntegrityError:
        db.rollback()


def _seed_demo_data(db: Session) -> None:
    manager = _ensure_user(db, "manager@example.com", "manager123", "Анна Смирнова", "manager")
    admin = _ensure_user(db, "admin@example.com", "admin123", "Саша Зубенко", "admin")
    db.flush()
    if db.scalar(select(Analysis.id).limit(1)):
        return
    demo_rows = [
        Analysis(owner_id=manager.id, text="Курьер опоздал, поддержка не отвечает. Срочно верните деньги.", customer_name="Ирина", channel="chat", creativity=0.3, max_tokens=160, sentiment="negative", score=-0.72, category="delivery", urgency="high", summary="Тон: negative. Клиент жалуется на доставку и отсутствие ответа.", suggested_reply="Приносим извинения за ситуацию. Передадим вопрос старшему специалисту.", metrics={"words": 8, "characters": 67, "sentences": 2, "average_word_length": 6.4, "readability_score": 58, "recommendations": ["Назначьте обращение команде: delivery.", "Задайте короткий SLA на ответ."], "confidence": 0.86, "explanations": ["опоздал", "не отвечает", "верните деньги"]}),
        Analysis(owner_id=manager.id, text="Спасибо, менеджер быстро помог с оплатой.", customer_name="Олег", channel="email", creativity=0.2, max_tokens=120, sentiment="positive", score=0.44, category="payment", urgency="normal", summary="Тон: positive. Клиент благодарит за помощь.", suggested_reply="Спасибо за обращение. Рады, что вопрос оплаты решён.", metrics={"words": 6, "characters": 39, "sentences": 1, "average_word_length": 5.7, "readability_score": 72, "recommendations": ["Сохраните позитивный тон."], "confidence": 0.74, "explanations": ["спасибо", "быстро"]}),
        Analysis(owner_id=admin.id, text="Товар пришел поврежденный, упаковка грязная.", customer_name="Мария", channel="marketplace", creativity=0.3, max_tokens=160, sentiment="negative", score=-0.55, category="quality", urgency="medium", summary="Тон: negative. Проблема качества товара.", suggested_reply="Приносим извинения за ситуацию. Проверим заказ и предложим решение.", metrics={"words": 6, "characters": 43, "sentences": 1, "average_word_length": 6.0, "readability_score": 65, "recommendations": ["Назначьте обращение команде: quality."], "confidence": 0.79, "explanations": ["поврежденный", "грязная"]}),
    ]
    db.add_all(demo_rows)


def _ensure_user(db: Session, email: str, password: str, name: str, role: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user:
        return user
    user = User(email=email, hashed_password=hash_password(password), name=name, role=role, company="Northwind Retail")
    db.add(user)
    db.flush()
    return user
