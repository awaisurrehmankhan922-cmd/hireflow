"""Application configuration, loaded from environment variables (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "HireFlow AI"
    database_url: str = "postgresql+psycopg2://hireflow:hireflow@db:5432/hireflow"

    # Security
    jwt_secret: str = "change-me"
    jwt_expire_minutes: int = 60 * 12
    webhook_secret: str = "change-me-webhook"  # shared with the WordPress plugin (HMAC)
    admin_email: str = "admin@example.com"
    admin_password: str = "change-me-now"

    # LLM provider: "ollama" (self-hosted, default), "anthropic" (Claude API) or "mock" (tests)
    llm_provider: str = "ollama"
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:8b"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-haiku-4-5"
    llm_timeout_seconds: int = 60
    confidence_threshold: float = 0.7

    # Email (one designated mailbox; more can be added as MailAccount rows later)
    imap_host: str = ""
    imap_port: int = 993
    imap_user: str = ""
    imap_password: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = "careers@example.com"
    mail_transport: str = "smtp"  # "smtp" | "log" (demo: records mail as sent without delivering)

    # Background worker
    worker_interval_seconds: int = 30
    open_webui_url: str = "/ai/"


@lru_cache
def get_settings() -> Settings:
    return Settings()
