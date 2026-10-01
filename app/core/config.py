"""Application configuration, loaded from environment variables."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. See `.env.example` for every recognized variable."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    rag_platform_base_url: str
    rag_platform_email: str
    rag_platform_password: str
    # Per-request override (AGT-013): when the MCP server subprocess is spawned on behalf of a
    # logged-in end user, this carries their already-issued access token so retrieval runs as
    # them, not the fixed service account above. Unset in the normal (no end-user auth) case.
    rag_platform_access_token: str | None = None

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3"

    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    max_verification_retries: int = 2


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide cached settings instance.

    Settings fields are loaded from environment variables or .env file via pydantic_settings.
    The # type: ignore[call-arg] suppresses a known mypy false positive: mypy sees Settings()
    called without required arguments, but pydantic_settings loads these from environment
    variables at runtime, which mypy's static analysis cannot see.
    """
    return Settings()  # type: ignore[call-arg]
