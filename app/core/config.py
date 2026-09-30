from urllib.parse import quote_plus

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SQLITE_URL = "sqlite+pysqlite:///./dev.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = ""
    postgres_password: str = ""
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_db: str = ""
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    storage_root: str = "./data/files"
    jwt_secret: str = "dev-only-change-me"
    jwt_expire_minutes: int = 720
    cors_origins: str = "http://localhost:5173"
    super_admin_email: str = "admin@example.com"
    super_admin_password: str = "change-me-please"
    seed_super_admin: bool = True
    inline_file_processing: bool = False
    auto_create_schema: bool = False
    max_upload_bytes: int = 20 * 1024 * 1024
    login_rate_limit: int = 10
    upload_rate_limit: int = 30
    rate_limit_window_seconds: int = 60
    rate_limit_enabled: bool = True

    @model_validator(mode="after")
    def assemble_database_url(self) -> "Settings":
        if self.database_url:
            return self
        if self.postgres_user and self.postgres_db:
            user = quote_plus(self.postgres_user)
            password = quote_plus(self.postgres_password)
            name = quote_plus(self.postgres_db)
            self.database_url = (
                f"postgresql+psycopg://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{name}"
            )
            return self
        self.database_url = _SQLITE_URL
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


_settings: Settings | None = None


def load_settings() -> Settings:
    global _settings
    _settings = Settings()
    return _settings


def get_settings() -> Settings:
    if _settings is None:
        return load_settings()
    return _settings
