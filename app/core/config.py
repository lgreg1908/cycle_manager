from pathlib import Path
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # repo root

ENV_FILE = os.getenv("ENV_FILE", str(BASE_DIR / ".env"))

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    APP_ENV: str = "local"
    DATABASE_URL: str
    CORS_ORIGINS: str = "*"  # Comma-separated list of allowed origins, or "*" for all

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS_ORIGINS into a list, handling '*' for development"""
        if self.CORS_ORIGINS == "*":
            return ["*"]
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

settings = Settings()
