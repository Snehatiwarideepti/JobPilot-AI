"""
JobPilot AI - Application Configuration
Loads all settings from environment variables via pydantic-settings.
"""
from functools import lru_cache
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    app_name: str = "JobPilot AI"
    environment: str = "development"
    log_level: str = "INFO"
    secret_key: str = "change-me-in-production"

    # ------------------------------------------------------------------ #
    # Backend server
    # ------------------------------------------------------------------ #
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    database_url: str = "postgresql+asyncpg://jobpilot:jobpilot_password@localhost:5432/jobpilot"
    database_sync_url: str = "postgresql://jobpilot:jobpilot_password@localhost:5432/jobpilot"
    postgres_user: str = "jobpilot"
    postgres_password: str = "jobpilot_password"
    postgres_db: str = "jobpilot"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # ------------------------------------------------------------------ #
    # LLM
    # ------------------------------------------------------------------ #
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"

    # ------------------------------------------------------------------ #
    # Job providers
    # ------------------------------------------------------------------ #
    jobvetta_api_key: Optional[str] = None
    jobvetta_base_url: str = "https://api.jobvetta.com/v1"
    jobvetta_timeout: int = 30
    jobvetta_max_retries: int = 3

    # ------------------------------------------------------------------ #
    # Embeddings
    # ------------------------------------------------------------------ #
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dimension: int = 384
    # Whether to use OpenAI embeddings instead of local sentence-transformers
    use_openai_embeddings: bool = False

    # ------------------------------------------------------------------ #
    # Retrieval weights (must sum to 1.0)
    # ------------------------------------------------------------------ #
    semantic_weight: float = 0.55
    skill_weight: float = 0.20
    experience_weight: float = 0.15
    location_weight: float = 0.10

    # ------------------------------------------------------------------ #
    # File upload
    # ------------------------------------------------------------------ #
    max_upload_size_mb: int = 10
    upload_dir: str = "./uploads"
    allowed_resume_extensions: str = ".pdf,.docx,.txt"

    @property
    def allowed_resume_exts(self) -> List[str]:
        return [e.strip() for e in self.allowed_resume_extensions.split(",") if e.strip()]

    # ------------------------------------------------------------------ #
    # Evaluation
    # ------------------------------------------------------------------ #
    eval_dataset: str = "wleeaf/career-site-job-postings-sample"

    # ------------------------------------------------------------------ #
    # Pagination defaults
    # ------------------------------------------------------------------ #
    default_page_size: int = 20
    max_page_size: int = 100

    model_config = {"env_file": (".env", "../.env"), "case_sensitive": False, "extra": "ignore"}


@lru_cache()
def get_settings() -> Settings:
    return Settings()
