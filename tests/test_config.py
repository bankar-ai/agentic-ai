"""Test application configuration loading."""


from app.core.config import get_settings


def test_settings_load_from_env(monkeypatch):
    monkeypatch.setenv("RAG_PLATFORM_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("RAG_PLATFORM_EMAIL", "svc@example.com")
    monkeypatch.setenv("RAG_PLATFORM_PASSWORD", "secret123")
    get_settings.cache_clear()

    settings = get_settings()

    assert settings.rag_platform_base_url == "http://localhost:8000"
    assert settings.rag_platform_email == "svc@example.com"
    assert settings.ollama_model == "qwen3"
    assert settings.max_verification_retries == 2
