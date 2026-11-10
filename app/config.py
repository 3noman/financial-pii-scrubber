from functools import lru_cache
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Centralized application settings loaded from environment variables (.env)."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application Metadata
    APP_NAME: str = "Financial Data Privacy Scrubber & AI Budget Analyzer"
    APP_ENV: str = "development"
    DEBUG: bool = False
    ALLOWED_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"

    # File Upload & Directory Paths
    MAX_FILE_SIZE_MB: int = Field(default=10, ge=1, le=50)
    MAX_FILES_PER_REQUEST: int = Field(default=10, ge=1, le=50)
    TEMP_UPLOAD_DIR: Path = BASE_DIR / "temp_uploads"
    DATA_DIR: Path = BASE_DIR / "data"
    OUTPUTS_DIR: Path = BASE_DIR / "outputs"

    # Database Settings
    POSTGRES_USER: str = "scrubber_user"
    POSTGRES_PASSWORD: str = "change_me_local_dev_password"
    POSTGRES_DB: str = "financial_scrubber_db"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = (
        "postgresql+psycopg://scrubber_user:change_me_local_dev_password"
        "@localhost:5432/financial_scrubber_db"
    )

    # Groq AI Settings
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_TIMEOUT_SECONDS: int = Field(default=30, ge=5, le=120)

    @property
    def max_file_size_bytes(self) -> int:
        return self.MAX_FILE_SIZE_MB * 1024 * 1024

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip()
            for origin in self.ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]


@lru_cache
def get_settings() -> Settings:
    """Returns a cached singleton instance of Settings."""
    settings = Settings()
    settings.TEMP_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    settings.OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    return settings
