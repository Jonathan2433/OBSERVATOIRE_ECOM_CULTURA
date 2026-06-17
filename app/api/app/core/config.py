"""Configuration de l'API, lue depuis l'environnement (12-factor)."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Paramètres de l'API. Valeurs surchargées par les variables d'environnement."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "production"
    # Connexions (fournies par docker-compose)
    database_url: str = "postgresql+psycopg://oes:oes@db:5432/oes"
    redis_url: str = "redis://redis:6379/0"
    # Sécurité
    secret_key: str = "dev-insecure-change-me"
    # CORS : en mono-poste, le front est servi par le même proxy -> origines locales.
    cors_origins: list[str] = ["http://localhost:8080", "http://127.0.0.1:8080"]


settings = Settings()
