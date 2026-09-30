from pydantic_ai.models.openai import OpenAIChatModel

from app.agents.llm import get_ollama_model
from app.core.config import Settings


def test_get_ollama_model_uses_configured_base_url_and_name():
    settings = Settings(
        rag_platform_base_url="http://localhost:8000",
        rag_platform_email="svc@example.com",
        rag_platform_password="secret123",
        ollama_base_url="http://localhost:11434/v1",
        ollama_model="qwen3",
    )

    model = get_ollama_model(settings)

    assert isinstance(model, OpenAIChatModel)
    assert model.model_name == "qwen3"
