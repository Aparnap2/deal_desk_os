from functools import lru_cache
from typing import List

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Deal Desk OS")
    environment: str = Field(default="development")
    secret_key: str = Field(default="change-me", min_length=12)
    access_token_expire_minutes: int = Field(default=60)
    database_url: str = Field(
        default="postgresql+asyncpg://deal_desk:deal_desk@localhost:5432/deal_desk_os",
    )
    redis_url: str = Field(default="redis://localhost:6379/0")
    allowed_origins: List[AnyHttpUrl] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
