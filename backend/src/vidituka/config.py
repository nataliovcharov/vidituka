from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# repo root, where .env lives next to docker-compose.yml
ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIDITUKA_", env_file=ENV_FILE, extra="ignore")

    database_url: str = "postgresql+psycopg://vidituka:vidituka@localhost:5433/vidituka"
    test_database_url: str | None = None
    http_user_agent: str = "vidituka/0.1 (+https://github.com/nataliovcharov/vidituka)"
    http_timeout_seconds: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
