from app.core.cors import CorsSettings, get_cors_settings


def test_default_allowed_origins_is_vite_dev_server():
    settings = CorsSettings()

    assert settings.allowed_origins_list == ["http://localhost:5173"]


def test_allowed_origins_list_splits_on_commas_and_strips_whitespace(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "https://example.vercel.app, http://localhost:5173")
    get_cors_settings.cache_clear()

    settings = get_cors_settings()

    assert settings.allowed_origins_list == ["https://example.vercel.app", "http://localhost:5173"]
    get_cors_settings.cache_clear()
