"""Configuración central. Todo se lee de variables de entorno (ver .env.example)."""
from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))  # type: ignore[arg-type]
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "si", "sí", "on"}


class Settings(BaseModel):
    app_name: str = "Asesor Pedagógico Inteligente"
    environment: str = "development"

    # Base de datos: SQLite local por defecto; PostgreSQL en producción.
    database_url: str = "sqlite:///./data/asesor.db"

    # Seguridad
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    token_minutes: int = 480
    cookie_secure: bool = False
    max_upload_mb: int = 25
    login_max_attempts: int = 8
    login_window_seconds: int = 300

    # Almacenamiento de archivos (fuera de la carpeta pública)
    storage_dir: Path = Path("./data/storage")

    # Conector de modelos (valores iniciales; el docente puede cambiarlos en la UI)
    llm_provider: str = "mock"  # mock | ollama | gemini | openai | anthropic
    llm_model: str = ""
    llm_base_url: str = ""
    llm_temperature: float = 0.0
    llm_seed: int = 42
    llm_timeout_s: int = 180
    llm_max_input_chars: int = 90_000
    openai_api_key: str | None = None
    openai_json_mode: str = "json_schema"  # json_schema | json_object
    anthropic_api_key: str | None = None
    gemini_api_key: str | None = None
    gemini_json_mode: str = "json_object"  # json_object | json_schema

    # Sandbox para ejecutar código subido
    sandbox_mode: str = "auto"  # auto | docker | unshare | rlimit
    sandbox_image: str = "asesor-sandbox:latest"
    sandbox_timeout_s: int = 60
    sandbox_memory_mb: int = 512
    sandbox_cpus: float = 1.0
    allow_rlimit_fallback: bool = True

    # GitHub
    github_token: str | None = None

    # Datos de demostración
    seed_demo: bool = True
    demo_password: str | None = None

    umbral_aprobacion: float = 3.0


@lru_cache
def get_settings() -> Settings:
    data: dict = {}
    mapping = {
        "APP_ENV": "environment",
        "DATABASE_URL": "database_url",
        "SECRET_KEY": "secret_key",
        "LLM_PROVIDER": "llm_provider",
        "LLM_MODEL": "llm_model",
        "LLM_BASE_URL": "llm_base_url",
        "OPENAI_API_KEY": "openai_api_key",
        "OPENAI_JSON_MODE": "openai_json_mode",
        "ANTHROPIC_API_KEY": "anthropic_api_key",
        "GEMINI_API_KEY": "gemini_api_key",
        "GEMINI_JSON_MODE": "gemini_json_mode",
        "SANDBOX_MODE": "sandbox_mode",
        "SANDBOX_IMAGE": "sandbox_image",
        "GITHUB_TOKEN": "github_token",
        "DEMO_PASSWORD": "demo_password",
    }
    for env_name, field in mapping.items():
        value = _env(env_name)
        if value is not None:
            data[field] = value
    if _env("STORAGE_DIR"):
        data["storage_dir"] = Path(_env("STORAGE_DIR"))  # type: ignore[arg-type]
    data["token_minutes"] = _env_int("TOKEN_MINUTES", 480)
    data["max_upload_mb"] = _env_int("MAX_UPLOAD_MB", 25)
    data["llm_timeout_s"] = _env_int("LLM_TIMEOUT_S", 180)
    data["llm_max_input_chars"] = _env_int("LLM_MAX_INPUT_CHARS", 90_000)
    data["sandbox_timeout_s"] = _env_int("SANDBOX_TIMEOUT_S", 60)
    data["sandbox_memory_mb"] = _env_int("SANDBOX_MEMORY_MB", 512)
    data["cookie_secure"] = _env_bool("COOKIE_SECURE", False)
    data["seed_demo"] = _env_bool("SEED_DEMO", True)
    data["allow_rlimit_fallback"] = _env_bool("ALLOW_RLIMIT_FALLBACK", True)

    # Railway entrega postgres:// ; SQLAlchemy necesita postgresql+psycopg://
    url = data.get("database_url", "")
    if url.startswith("postgres://"):
        data["database_url"] = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        data["database_url"] = "postgresql+psycopg://" + url[len("postgresql://"):]

    settings = Settings(**data)
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    if settings.database_url.startswith("sqlite:///"):
        Path(settings.database_url.replace("sqlite:///", "")).parent.mkdir(parents=True, exist_ok=True)
    return settings
