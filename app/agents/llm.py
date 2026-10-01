"""Shared PydanticAI model factory. `get_model` dispatches on `settings.llm_provider`: "ollama"
(default, local dev, free) or "openrouter" (AGT-004 -- the deployment target has no room to run
Ollama; see docs/architecture.md's "Deployment" section for why).
"""

from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openrouter import OpenRouterProvider

from app.core.config import Settings


def get_ollama_model(settings: Settings) -> OpenAIChatModel:
    """Build a PydanticAI model pointed at Ollama's OpenAI-compatible endpoint.

    Ollama serves an OpenAI-compatible API at `/v1`, using OllamaProvider to configure
    the base URL. The provider handles all necessary setup for connecting to the local
    Ollama instance.
    """
    provider = OllamaProvider(base_url=settings.ollama_base_url)
    return OpenAIChatModel(settings.ollama_model, provider=provider)


def get_openrouter_model(settings: Settings) -> Model:
    """Build a PydanticAI model pointed at OpenRouter.

    Free-tier OpenRouter models get rate-limited hard and rotate out of the free catalog without
    warning (per OpenRouter's own guidance), so `settings.openrouter_fallback_model`, when set,
    wraps the primary model in a `FallbackModel`: a request that fails with a `ModelAPIError`
    (rate limit, model temporarily unavailable, etc.) on the primary is retried against the
    fallback automatically, rather than failing the whole query.
    """
    provider = OpenRouterProvider(api_key=settings.openrouter_api_key)
    primary = OpenAIChatModel(settings.openrouter_model, provider=provider)
    if not settings.openrouter_fallback_model:
        return primary
    fallback = OpenAIChatModel(settings.openrouter_fallback_model, provider=provider)
    return FallbackModel(primary, fallback)


def get_model(settings: Settings) -> Model:
    """Dispatch to the configured LLM provider."""
    if settings.llm_provider == "openrouter":
        return get_openrouter_model(settings)
    return get_ollama_model(settings)
