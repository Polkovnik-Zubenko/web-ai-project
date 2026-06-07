import logging
import re
import time
from dataclasses import dataclass

from app.config import settings
from app.errors import PromptRejectedError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelResult:
    sentiment: str
    score: float
    summary: str
    recommendations: list[str]
    metrics: dict


class TextInsightModel:
    # Изоляция ML-логики
    def __init__(self, max_text_length: int, max_tokens: int) -> None:
        self.max_text_length = max_text_length
        self.max_tokens = max_tokens
        self.ready = False
        self.positive_words = {"good", "great", "fast", "clear", "useful", "love", "excellent", "понятный", "быстро", "хороший", "удобный"}
        self.negative_words = {"bad", "slow", "error", "fail", "broken", "hate", "unclear", "плохо", "ошибка", "медленно", "сломано"}

    def load(self) -> None:
        started = time.perf_counter()
        self.ready = True
        logger.info("model_loaded elapsed_ms=%.2f", (time.perf_counter() - started) * 1000)

    def generate(self, text: str, creativity: float, max_tokens: int) -> ModelResult:
        started = time.perf_counter()
        # Управление ресурсами
        if len(text) > self.max_text_length:
            raise PromptRejectedError(f"Текст длиннее допустимого лимита: {self.max_text_length} символов.")
        if max_tokens > self.max_tokens:
            raise PromptRejectedError(f"max_tokens не должен превышать {self.max_tokens}.")

        words = re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", text.lower())
        sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
        pos = sum(word in self.positive_words for word in words)
        neg = sum(word in self.negative_words for word in words)
        score = 0.0 if not words else max(-1.0, min(1.0, (pos - neg) / max(1, pos + neg + 2)))
        sentiment = "positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"
        avg_word_len = round(sum(len(w) for w in words) / max(1, len(words)), 2)
        readability = round(max(0, min(100, 100 - avg_word_len * 8 - max(0, len(words) / max(1, len(sentences)) - 18) * 1.5)), 2)

        recommendations = self._recommend(sentiment, readability, creativity)
        summary = self._summarize(text, sentiment, readability, max_tokens)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("model_inference sentiment=%s score=%.3f elapsed_ms=%.2f", sentiment, score, elapsed_ms)

        return ModelResult(
            sentiment=sentiment,
            score=round(score, 3),
            summary=summary,
            recommendations=recommendations,
            metrics={
                "characters": len(text),
                "words": len(words),
                "sentences": max(1, len(sentences)),
                "average_word_length": avg_word_len,
                "readability_score": readability,
            },
        )

    def _summarize(self, text: str, sentiment: str, readability: float, max_tokens: int) -> str:
        clean = " ".join(text.split())
        first = clean[: max(80, min(len(clean), max_tokens * 3))]
        return f"Тон: {sentiment}. Читабельность: {readability}/100. Ключевой фрагмент: {first}"

    def _recommend(self, sentiment: str, readability: float, creativity: float) -> list[str]:
        base = []
        if readability < 55:
            base.append("Разбейте длинные предложения и уберите лишние вводные конструкции.")
        else:
            base.append("Структура текста выглядит достаточно простой для чтения.")
        if sentiment == "negative":
            base.append("Добавьте больше конкретики о решении проблемы и ожидаемом результате.")
        elif sentiment == "positive":
            base.append("Сохраните позитивный тон, но подкрепите его фактами или метриками.")
        else:
            base.append("Уточните позицию текста: сейчас он воспринимается нейтрально.")
        if creativity > 0.6:
            base.append("Можно усилить подачу метафорой, примером пользователя или коротким слоганом.")
        return base


def build_model() -> TextInsightModel:
    return TextInsightModel(max_text_length=settings.max_text_length, max_tokens=settings.max_tokens)
