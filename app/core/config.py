from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Fieldline CRM"
    environment: str = "development"
    debug: bool = False
    database_url: str = "postgresql+psycopg://fieldline:fieldline@localhost:5432/fieldline"
    api_prefix: str = "/api/v1"
    jwt_secret_key: str = "development-only-change-me-development-only"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "fieldline-api"
    jwt_audience: str = "fieldline-web"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7
    secure_cookies: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="FIELDLINE_",
        extra="ignore",
    )

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if (
            self.environment == "production"
            and self.jwt_secret_key == "development-only-change-me-development-only"
        ):
            raise ValueError("FIELDLINE_JWT_SECRET_KEY must be changed in production")
        if len(self.jwt_secret_key.encode("utf-8")) < 32:
            raise ValueError("FIELDLINE_JWT_SECRET_KEY must be at least 32 bytes")
        if self.environment == "production" and not self.secure_cookies:
            raise ValueError("FIELDLINE_SECURE_COOKIES must be true in production")
        if not 5 <= self.access_token_expire_minutes <= 60:
            raise ValueError("Access token lifetime must be between 5 and 60 minutes")
        if not 1 <= self.refresh_token_expire_days <= 30:
            raise ValueError("Refresh token lifetime must be between 1 and 30 days")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
