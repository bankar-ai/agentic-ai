"""Application configuration, loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. See `.env.example` for every recognized variable."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    rag_platform_base_url: str
    rag_platform_email: str
    rag_platform_password: str

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3"

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    max_verification_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached settings instance."""
    return Settings()
