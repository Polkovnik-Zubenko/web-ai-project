from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AnalyzeRequest(BaseModel):
    # Валидация данных
    text: str = Field(
        min_length=10,
        max_length=4000,
        description="Текст для анализа",
        examples=["FastAPI помогает быстро собрать понятный ML API."],
    )
    creativity: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Насколько свободно формировать рекомендации: 0.0 - строго, 1.0 - креативно",
        examples=[0.3],
    )
    max_tokens: int = Field(
        default=256,
        ge=32,
        le=1024,
        description="Ограничение длины текстового ответа модели",
        examples=[160],
    )


class TicketRequest(AnalyzeRequest):
    customer_name: str = Field(default="Клиент", min_length=1, max_length=120, description="Имя клиента")
    channel: Literal["web", "email", "chat", "marketplace", "phone"] = Field(default="web", description="Канал обращения")


class TextMetrics(BaseModel):
    characters: int
    words: int
    sentences: int
    average_word_length: float
    readability_score: float


class AnalyzeResponse(BaseModel):
    id: int
    sentiment: Literal["positive", "neutral", "negative"]
    category: Literal["delivery", "payment", "quality", "service", "other"]
    urgency: Literal["normal", "medium", "high"]
    score: float = Field(ge=-1.0, le=1.0)
    summary: str
    suggested_reply: str
    recommendations: list[str]
    metrics: TextMetrics
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisListItem(BaseModel):
    id: int
    owner_id: int | None = None
    customer_name: str
    channel: str
    sentiment: str
    category: str
    urgency: str
    score: float
    summary: str
    suggested_reply: str
    metrics: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
    redis: Literal["ok", "error"]
    model: Literal["ready", "error"]


class TaskCreatedResponse(BaseModel):
    task_id: str
    status: Literal["queued"]
    status_url: str
    websocket_url: str


class TaskStatusResponse(BaseModel):
    task_id: str
    state: str
    progress: int = Field(ge=0, le=100)
    stage: str
    ticket_id: int | None = None
    result: dict[str, Any] | None = None


class RegisterRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255, examples=["manager@example.com"])
    password: str = Field(min_length=6, max_length=72, examples=["manager123"])
    name: str = Field(min_length=2, max_length=120, examples=["Анна Смирнова"])
    company: str = Field(default="Northwind Retail", min_length=2, max_length=120)


class LoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=255)
    password: str = Field(min_length=6, max_length=72)


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: str
    company: str

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserResponse
