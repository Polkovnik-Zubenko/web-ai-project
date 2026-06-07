from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "AI Web Text Service"
    environment: str = "local"
    database_url: str = "postgresql+psycopg://ai_web:ai_web_password@postgres:5432/ai_web"
    redis_url: str = "redis://redis:6379/0"
    max_text_length: int = Field(default=4000, ge=100, le=20000)
    max_tokens: int = Field(default=256, ge=32, le=1024)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
