"""Shared PydanticAI model factory: every agent talks to the same local Ollama instance."""

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from app.core.config import Settings


def get_ollama_model(settings: Settings) -> OpenAIChatModel:
    """Build a PydanticAI model pointed at Ollama's OpenAI-compatible endpoint.

    Ollama serves an OpenAI-compatible API at `/v1`, using OllamaProvider to configure
    the base URL. The provider handles all necessary setup for connecting to the local
    Ollama instance.
    """
    provider = OllamaProvider(base_url=settings.ollama_base_url)
    return OpenAIChatModel(settings.ollama_model, provider=provider)
