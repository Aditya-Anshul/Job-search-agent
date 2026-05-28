"""Pydantic Settings singleton — single source of truth for all configuration."""

from typing import Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Type-safe configuration loaded from environment variables / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── LLM Provider ─────────────────────────────────────────────
    llm_provider: str = "placeholder" # placeholder | ollama | groq | gemini | deepseek | huggingface | openai

    # Provider-specific keys
    huggingface_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    deepseek_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    
    # Models
    huggingface_model: str = "mistralai/Mistral-7B-Instruct-v0.3"
    groq_model: str = "llama3-70b-8192"
    gemini_model: str = "gemini-1.5-flash"
    deepseek_model: str = "deepseek-chat"
    openai_model: str = "gpt-4o-mini"
    
    # Provider Base URLs
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    deepseek_base_url: str = "https://api.deepseek.com/v1"

    # ── Platform Credentials ──────────────────────────────────────
    naukri_email: Optional[str] = None
    naukri_password: Optional[str] = None
    monster_email: Optional[str] = None
    monster_password: Optional[str] = None
    joindevops_email: Optional[str] = None
    joindevops_password: Optional[str] = None
    linkedin_email: Optional[str] = None
    linkedin_password: Optional[str] = None

    # ── Telegram ─────────────────────────────────────────────────
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # ── Job Preferences ───────────────────────────────────────────
    job_roles: str = "DevOps Engineer,Cloud Engineer,MLOps Engineer,Platform Engineer"
    job_locations: str = "India,Remote,Hybrid"
    experience_years: float = 3.5
    job_freshness_days: int = 2

    # ── Application Settings ──────────────────────────────────────
    match_threshold: int = 70
    max_applications_per_run: int = 30
    apply_easy_apply_only: bool = False
    run_hour: int = 9
    run_timezone: str = "Asia/Kolkata"
    follow_companies: bool = False
    blacklist_companies: str = ""

    @property
    def blacklist_companies_list(self) -> list[str]:
        """Return blacklist_companies as a parsed list, stripping whitespace."""
        return [c.strip() for c in self.blacklist_companies.split(",") if c.strip()]

    # ── Paths ─────────────────────────────────────────────────────
    resume_pdf_path: str = "resume/uploads/resume.pdf"
    resume_docx_path: str = "resume/uploads/resume.docx"
    database_url: str = "sqlite:///data/job_agent.db"

    # ── Anti-Detection ────────────────────────────────────────────
    min_delay_seconds: float = 3.0
    max_delay_seconds: float = 12.0
    headless: bool = True

    # ── Property Helpers ──────────────────────────────────────────

    @property
    def job_roles_list(self) -> list[str]:
        """Return job_roles as a parsed list, stripping whitespace."""
        return [r.strip() for r in self.job_roles.split(",") if r.strip()]

    @property
    def job_locations_list(self) -> list[str]:
        """Return job_locations as a parsed list, stripping whitespace."""
        return [loc.strip() for loc in self.job_locations.split(",") if loc.strip()]

    # ── Validators ────────────────────────────────────────────────

    @field_validator("telegram_bot_token", mode="before")
    @classmethod
    def warn_missing_telegram(cls, v: Optional[str]) -> Optional[str]:
        if not v or v == "your_telegram_bot_token_here":
            return None
        return v

    @field_validator("run_hour", mode="before")
    @classmethod
    def validate_run_hour(cls, v: int) -> int:
        hour = int(v)
        if not 0 <= hour <= 23:
            raise ValueError(f"RUN_HOUR must be 0-23, got {hour}")
        return hour


# Module-level singleton — import with: from config.settings import settings
settings = Settings()
