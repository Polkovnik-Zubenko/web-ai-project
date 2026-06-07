from redis import Redis

from app.ml.text_model import TextInsightModel


class AppState:
    model: TextInsightModel | None = None
    redis: Redis | None = None


state = AppState()
