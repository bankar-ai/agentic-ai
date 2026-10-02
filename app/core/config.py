"""Application configuration, loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. See `.env.example` for every recognized variable."""

    # extra="ignore": AGT-017 added a second settings class (`app.core.cors.CorsSettings`) that
    # shares this same `.env` file for its own `CORS_*` variable -- without this, pydantic-
    # settings' default "forbid" on every key found in the dotenv file would reject this class's
    # otherwise-unrelated keys.
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    rag_platform_base_url: str
    rag_platform_email: str
    rag_platform_password: str
    # Per-request override (AGT-013): when the MCP server subprocess is spawned on behalf of a
    # logged-in end user, these carry their already-established session (a cookie value + CSRF
    # token, post-ERP-116 -- see app/rag_client/auth.py's module docstring) so retrieval runs as
    # them, not the fixed service account above. Both or neither; unset in the normal case.
    rag_platform_access_token: str | None = None
    rag_platform_csrf_token: str | None = None

    # AGT-004: "ollama" (default, local dev/free) or "openrouter" (deployment -- the local VM
    # this project deploys alongside has no room to run Ollama; see docs/architecture.md).
    llm_provider: Literal["ollama", "openrouter"] = "ollama"

    ollama_base_url: str = "http://localhost:11434/v1"
    ollama_model: str = "qwen3"

    openrouter_api_key: str | None = None
    # Both free-tier, both from a model family OpenRouter positions for agentic/tool-calling use
    # (see .ai/sessions/ around 2026-10-01 for the research). Free-tier models get rate-limited
    # hard and rotate without warning, so a second model is a real fallback, not a nicety --
    # see get_model()'s FallbackModel wiring in app/agents/llm.py.
    openrouter_model: str = "nvidia/nemotron-3-nano-30b-a3b:free"
    openrouter_fallback_model: str | None = "nvidia/nemotron-3.5-lightning:free"

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
