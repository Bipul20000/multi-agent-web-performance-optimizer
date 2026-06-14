"""Application settings loaded from environment variables via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration — values are read from ``.env`` / environment.

    All fields have sensible defaults so the app can start in development
    without a fully populated ``.env`` file.  Production deployments should
    set every key explicitly.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # ── Google Gemini & Groq ───────────────────────────────────────────────
    GEMINI_API_KEY: str = ""
    GROQ_API_KEY: str = ""

    # ── GitHub ─────────────────────────────────────────────────────────────
    GITHUB_TOKEN: str = ""
    GITHUB_REPO: str = ""  # e.g. "username/my-demo-site"

    # ── Target Website ─────────────────────────────────────────────────────
    WEBSITE_URL: str = ""  # e.g. "https://my-demo.vercel.app"

    # ── PageSpeed Insights ─────────────────────────────────────────────────
    PSI_API_KEY: str = ""

    # ── MongoDB ────────────────────────────────────────────────────────────
    MONGODB_URI: str = "mongodb://localhost:27017"
    DB_NAME: str = "awpis"

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6379"

    # ── LangSmith Observability ────────────────────────────────────────────
    LANGSMITH_API_KEY: str = ""
    LANGCHAIN_PROJECT: str = "awpis-demo"

    # ── Vercel Deploy ──────────────────────────────────────────────────────
    VERCEL_TOKEN: str = ""

    # ── Run Mode ───────────────────────────────────────────────────────────
    RUN_MODE: str = "SUPERVISED"  # "SUPERVISED" or "AUTOMATED"
    DEMO_MODE: str = "false"

    # ── Operational tunables ───────────────────────────────────────────────
    MAX_RETRIES: int = 3
    PSI_TIMEOUT: int = 60  # seconds
    SANDBOX_TIMEOUT: int = 300  # seconds
    LOG_LEVEL: str = "INFO"


# ── Singleton accessor ─────────────────────────────────────────────────────

_settings: Settings | None = None


def get_settings() -> Settings:
    """Return a cached Settings instance (singleton per process)."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
