from pathlib import Path

from app.config import Settings


def test_blank_app_name_uses_default(monkeypatch):
    monkeypatch.setenv("APP_NAME", "")
    settings = Settings()
    assert settings.app_name == "SuperVideoEditorAI"


def test_blank_environment_uses_default(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "")
    settings = Settings()
    assert settings.environment == "development"


def test_blank_api_prefix_uses_default(monkeypatch):
    monkeypatch.setenv("API_PREFIX", "")
    settings = Settings()
    assert settings.api_prefix == "/api/v1"


def test_blank_cors_origins_uses_default(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "")
    settings = Settings()
    assert settings.cors_origins == "http://localhost:3000,http://localhost:5173"


def test_blank_max_upload_bytes_uses_default(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "")
    settings = Settings()
    assert settings.max_upload_bytes == 524_288_000


def test_explicit_max_upload_bytes_is_preserved(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "123456")
    settings = Settings()
    assert settings.max_upload_bytes == 123456


def test_blank_storage_root_uses_writable_vercel_path(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("STORAGE_ROOT", "")
    settings = Settings()
    assert settings.storage_root == Path("/tmp/supervideoeditorai")


def test_blank_storage_root_keeps_local_default(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setenv("STORAGE_ROOT", "")
    settings = Settings()
    assert settings.storage_root == Path("storage")
