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


class TextMetrics(BaseModel):
    characters: int
    words: int
    sentences: int
    average_word_length: float
    readability_score: float


class AnalyzeResponse(BaseModel):
    id: int
    sentiment: Literal["positive", "neutral", "negative"]
    score: float = Field(ge=-1.0, le=1.0)
    summary: str
    recommendations: list[str]
    metrics: TextMetrics
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AnalysisListItem(BaseModel):
    id: int
    sentiment: str
    score: float
    summary: str
    metrics: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "error"]
    redis: Literal["ok", "error"]
    model: Literal["ready", "error"]
