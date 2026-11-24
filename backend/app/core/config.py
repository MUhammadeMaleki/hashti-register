from pathlib import Path
from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="HASHTI_",
        env_file=BACKEND_DIR / ".env",
        extra="ignore",
        hide_input_in_errors=True,
    )

    environment: str = "development"
    database_url: SecretStr
    test_database_url: SecretStr | None = None
    auth_secret: SecretStr | None = None
    public_origin: str = "http://127.0.0.1:3000"
    argon2_time_cost: int = Field(default=3, ge=1, le=10)
    argon2_memory_cost: int = Field(default=65536, ge=8192)
    argon2_parallelism: int = Field(default=4, ge=1, le=16)
    login_max_failures: int = Field(default=5, ge=1)
    login_lock_minutes: int = Field(default=15, ge=1)

    @field_validator("database_url", "test_database_url")
    @classmethod
    def require_postgresql(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            try:
                url = make_url(value.get_secret_value())
                valid = url.drivername == "postgresql+psycopg" and bool(url.database)
            except Exception:
                valid = False
            if not valid:
                raise ValueError("A postgresql+psycopg URL with a database name is required")
        return value

    @field_validator("auth_secret")
    @classmethod
    def require_random_secret(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            secret = value.get_secret_value()
            if len(secret) != 64 or any(
                character not in "0123456789abcdefABCDEF" for character in secret
            ):
                raise ValueError("HASHTI_AUTH_SECRET must be 64 random hex characters")
        return value

    @field_validator("public_origin")
    @classmethod
    def require_origin(cls, value: str) -> str:
        from urllib.parse import urlparse

        parsed = urlparse(value)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("HASHTI_PUBLIC_ORIGIN must be a single HTTP(S) origin")
        return value.rstrip("/")

    @model_validator(mode="after")
    def require_production_https(self) -> Self:
        if self.environment != "development" and not self.public_origin.startswith("https://"):
            raise ValueError("HTTPS origin is required outside development")
        return self
