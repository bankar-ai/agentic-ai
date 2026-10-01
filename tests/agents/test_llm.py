from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel

from app.agents.llm import get_model, get_ollama_model, get_openrouter_model
from app.core.config import Settings


def _base_settings(**overrides) -> Settings:
    defaults = {
        "rag_platform_base_url": "http://localhost:8000",
        "rag_platform_email": "svc@example.com",
        "rag_platform_password": "secret123",
    }
    return Settings(**{**defaults, **overrides})


def test_get_ollama_model_uses_configured_base_url_and_name():
    settings = _base_settings(ollama_base_url="http://localhost:11434/v1", ollama_model="qwen3")

    model = get_ollama_model(settings)

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "qwen3"


def test_get_openrouter_model_wraps_primary_and_fallback_in_fallback_model():
    settings = _base_settings(
        openrouter_api_key="sk-or-test",
        openrouter_model="nvidia/nemotron-3-nano-30b-a3b:free",
        openrouter_fallback_model="nvidia/nemotron-3.5-lightning:free",
    )

    model = get_openrouter_model(settings)

    assert isinstance(model, FallbackModel)
    names = [m.model_name for m in model.models]
    assert names == ["nvidia/nemotron-3-nano-30b-a3b:free", "nvidia/nemotron-3.5-lightning:free"]


def test_get_openrouter_model_without_fallback_returns_bare_model():
    settings = _base_settings(
        openrouter_api_key="sk-or-test",
        openrouter_model="nvidia/nemotron-3-nano-30b-a3b:free",
        openrouter_fallback_model=None,
    )

    model = get_openrouter_model(settings)

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "nvidia/nemotron-3-nano-30b-a3b:free"


def test_get_model_dispatches_to_ollama_by_default():
    settings = _base_settings(ollama_model="qwen3")

    model = get_model(settings)

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "qwen3"


def test_get_model_dispatches_to_openrouter_when_configured():
    settings = _base_settings(
        llm_provider="openrouter",
        openrouter_api_key="sk-or-test",
        openrouter_model="nvidia/nemotron-3-nano-30b-a3b:free",
        openrouter_fallback_model=None,
    )

    model = get_model(settings)

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "nvidia/nemotron-3-nano-30b-a3b:free"
