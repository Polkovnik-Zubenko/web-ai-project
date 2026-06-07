import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

from app.config import settings
from app.errors import PromptRejectedError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelResult:
    sentiment: str
    score: float
    category: str
    urgency: str
    summary: str
    suggested_reply: str
    recommendations: list[str]
    metrics: dict


class TextInsightModel:
    # Изоляция ML-логики
    def __init__(self, max_text_length: int, max_tokens: int) -> None:
        self.max_text_length = max_text_length
        self.max_tokens = max_tokens
        self.ready = False
        self.onnx_session = None
        self.positive_words = {"good", "great", "fast", "clear", "useful", "love", "excellent", "понятный", "быстро", "хороший", "удобный"}
        self.negative_words = {
            "bad", "slow", "error", "fail", "broken", "hate", "unclear",
            "плохо", "ужасно", "отвратительно", "ошибка", "медленно", "сломано",
            "опоздал", "опоздала", "опоздали", "жду", "верните", "жалоба",
            "не отвечает", "нет ответа", "не работает", "не пришел", "не пришёл",
            "не доставили", "не получил", "не получила", "сорвали", "разочарован",
        }
        self.negative_stems = {
            "плох", "ужас", "отврат", "ошиб", "медлен", "сломан", "опозд",
            "задерж", "вернит", "возврат", "жалоб", "груб", "разочар",
            "неработ", "поврежд", "брак", "сорван", "проблем",
        }
        self.positive_stems = {"хорош", "быстр", "удоб", "понят", "спасибо", "помог", "отлич", "довол"}
        self.category_terms = {
            "delivery": {"доставка", "курьер", "посылка", "срок", "опоздал", "shipping", "delivery"},
            "payment": {"оплата", "карта", "деньги", "чек", "возврат", "payment", "refund", "invoice"},
            "quality": {"качество", "сломано", "брак", "поврежден", "грязный", "quality", "broken"},
            "service": {"менеджер", "поддержка", "оператор", "ответ", "груб", "support", "service"},
        }
        self.urgent_terms = {"срочно", "немедленно", "жалоба", "верните", "суд", "urgent", "asap", "refund", "отмена"}

    def load(self) -> None:
        started = time.perf_counter()
        # Оптимизация инференса
        try:
            import onnxruntime as ort

            model_path = Path("/app/model_cache/customer_feedback_model.onnx")
            if not model_path.exists():
                from app.ml.train_model import main as train_model

                train_model()
            if model_path.exists():
                self.onnx_session = ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
        except Exception:
            logger.exception("onnx_load_failed_using_rule_fallback")
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
        pos = self._positive_score(words, text.lower())
        neg = self._negative_score(words, text.lower())
        score = 0.0 if not words else max(-1.0, min(1.0, (pos - neg) / max(1, pos + neg + 1)))
        sentiment = "positive" if score > 0.12 else "negative" if score < -0.12 else "neutral"
        avg_word_len = round(sum(len(w) for w in words) / max(1, len(words)), 2)
        readability = round(max(0, min(100, 100 - avg_word_len * 8 - max(0, len(words) / max(1, len(sentences)) - 18) * 1.5)), 2)

        category = self._classify_category(words)
        urgency = self._classify_urgency(words, sentiment, readability)
        recommendations = self._recommend(sentiment, readability, creativity, category, urgency)
        summary = self._summarize(text, sentiment, readability, max_tokens)
        suggested_reply = self._reply(sentiment, category, urgency)
        elapsed_ms = (time.perf_counter() - started) * 1000
        logger.info("model_inference sentiment=%s score=%.3f elapsed_ms=%.2f", sentiment, score, elapsed_ms)

        return ModelResult(
            sentiment=sentiment,
            score=round(score, 3),
            category=category,
            urgency=urgency,
            summary=summary,
            suggested_reply=suggested_reply,
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

    def _classify_category(self, words: list[str]) -> str:
        if self.onnx_session is not None:
            try:
                import numpy as np

                features = np.array([self._feature_vector(words)], dtype=np.float32)
                scores = self.onnx_session.run(["scores"], {"features": features})[0][0]
                labels = ["delivery", "payment", "quality", "service", "other"]
                return labels[int(scores.argmax())]
            except Exception:
                logger.exception("onnx_inference_failed_using_rule_fallback")
        scores = {category: sum(word in terms for word in words) for category, terms in self.category_terms.items()}
        category, value = max(scores.items(), key=lambda item: item[1])
        return category if value > 0 else "other"

    def _positive_score(self, words: list[str], lowered_text: str) -> float:
        exact = sum(word in self.positive_words for word in words)
        stems = sum(any(word.startswith(stem) for stem in self.positive_stems) for word in words)
        return exact + 0.8 * stems

    def _negative_score(self, words: list[str], lowered_text: str) -> float:
        exact = sum(word in self.negative_words for word in words)
        stems = sum(any(word.startswith(stem) for stem in self.negative_stems) for word in words)
        phrases = sum(phrase in lowered_text for phrase in self.negative_words if " " in phrase)
        negation = 0
        for index, word in enumerate(words[:-1]):
            if word in {"не", "нет", "никто", "никак"}:
                next_word = words[index + 1]
                if next_word not in {"плохо", "ужасно"}:
                    negation += 1
        exclamations = min(2, lowered_text.count("!")) * 0.25
        return exact + 0.9 * stems + 1.5 * phrases + 0.8 * negation + exclamations

    def _feature_vector(self, words: list[str]) -> list[float]:
        return [
            float(sum(word in self.category_terms["delivery"] for word in words)),
            float(sum(word in self.category_terms["payment"] for word in words)),
            float(sum(word in self.category_terms["quality"] for word in words)),
            float(sum(word in self.category_terms["service"] for word in words)),
            float(self._negative_score(words, " ".join(words))),
            float(sum(word in self.urgent_terms for word in words)),
        ]

    def _classify_urgency(self, words: list[str], sentiment: str, readability: float) -> str:
        urgent_hits = sum(word in self.urgent_terms for word in words)
        if urgent_hits >= 2 or sentiment == "negative" and urgent_hits >= 1:
            return "high"
        if sentiment == "negative" or readability < 45:
            return "medium"
        return "normal"

    def _reply(self, sentiment: str, category: str, urgency: str) -> str:
        category_ru = {
            "delivery": "доставки",
            "payment": "оплаты",
            "quality": "качества товара",
            "service": "работы поддержки",
            "other": "обращения",
        }[category]
        prefix = "Приносим извинения за ситуацию" if sentiment == "negative" else "Спасибо за обращение"
        priority = "Мы передадим вопрос старшему специалисту в приоритетном порядке." if urgency == "high" else "Мы проверим детали и вернёмся с ответом."
        return f"{prefix}. Видим, что вопрос касается {category_ru}. {priority}"

    def _recommend(self, sentiment: str, readability: float, creativity: float, category: str, urgency: str) -> list[str]:
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
        if category != "other":
            base.append(f"Назначьте обращение команде: {category}.")
        if urgency == "high":
            base.append("Пометьте обращение как приоритетное и задайте короткий SLA на ответ.")
        return base


def build_model() -> TextInsightModel:
    return TextInsightModel(max_text_length=settings.max_text_length, max_tokens=settings.max_tokens)
