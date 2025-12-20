from pathlib import Path
import os
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]  # repo root

ENV_FILE = os.getenv("ENV_FILE", str(BASE_DIR / ".env"))

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, extra="ignore")

    APP_ENV: str = "local"
    DATABASE_URL: str

settings = Settings()
