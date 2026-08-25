from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


def _normalize_auth_tenant_key(value: str) -> str:
    normalized = value.strip().lower()
    if normalized == "":
        raise ValueError("auth_tenant_key 不能为空")
    return normalized


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/bid_agent_dev"
    allowed_origins: list[str] = ["http://localhost:8000"]
    session_cookie_name: str = "bid_session"
    csrf_cookie_name: str = "bid_csrf"
    session_cookie_secure: bool = False
    session_cookie_domain: str | None = None
    session_idle_minutes: int = 30
    session_absolute_hours: int = 8
    auth_tenant_key: str = "yunqi"
    login_failure_limit: int = 5
    login_failure_window_seconds: int = 900
    redis_url: str | None = None
    mcp_endpoint: str = "http://mcp-tools:8000/mcp"
    mcp_service_token: str | None = None
    mineru_endpoint: str = "http://mineru:8000"
    minio_endpoint: str | None = None
    minio_access_key: str | None = None
    minio_secret_key: str | None = None
    minio_bucket_name: str = "bid-agent-files"
    minio_secure: bool = False

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def _parse_allowed_origins(cls, value: object) -> object:
        if isinstance(value, str):
            origins = [item.strip() for item in value.split(",") if item.strip()]
            return origins or ["http://localhost:8000"]
        return value

    @field_validator("auth_tenant_key", mode="before")
    @classmethod
    def _validate_auth_tenant_key(cls, value: object) -> str:
        if not isinstance(value, str):
            raise TypeError("auth_tenant_key 必须是字符串")
        return _normalize_auth_tenant_key(value)

    @model_validator(mode="after")
    def _validate_test_database_name(self) -> Settings:
        if self.app_env != "test":
            return self

        database_name = make_url(self.database_url).database
        if not database_name or "_test" not in database_name:
            raise ValueError("测试环境 database_url 必须使用包含 _test 的数据库名")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
