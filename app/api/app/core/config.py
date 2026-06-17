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

    # --- Authentification (L1) ---
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 480          # session de travail ~8h
    session_cookie_name: str = "oes_session"
    cookie_secure: bool = False                      # localhost en http (mono-poste)
    # Anti-bruteforce (verrouillage temporaire)
    max_login_attempts: int = 5
    lockout_minutes: int = 5
    # Admin initial créé au démarrage si la base ne contient aucun utilisateur
    admin_username: str = "admin"
    admin_password: str = ""                         # vide -> défaut + avertissement

    # --- Traitement par lots (L2) ---
    uploads_dir: str = "/data/uploads"               # fichiers déposés (partagé avec worker)
    output_dir: str = "/data/output"                 # CSV enrichis (export L4)
    taxonomy_path: str = "/app/taxonomy.json"        # référentiel (listes contraintes de la revue)
    job_queue: str = "default"
    job_timeout_seconds: int = 7200                  # 2h max par lot
    max_upload_mb: int = 60


settings = Settings()
