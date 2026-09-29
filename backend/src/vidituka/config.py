from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VIDITUKA_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://vidituka:vidituka@localhost:5432/vidituka"
    http_user_agent: str = "vidituka/0.1 (+https://github.com/CHANGE-ME/vidituka)"
    http_timeout_seconds: float = 20.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
