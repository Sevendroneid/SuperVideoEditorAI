import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SuperVideoEditorAI"
    environment: str = "development"
    log_level: str = "INFO"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:3000,http://localhost:5173"
    max_upload_bytes: int = 524_288_000
    storage_root: Path = Path("./storage")
    redis_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    ai_provider: str = "disabled"
    ai_base_url: str | None = None
    ai_api_key: str | None = Field(default=None, repr=False)
    ai_model: str | None = None
    ffmpeg_bin: str = "ffmpeg"
    ffprobe_bin: str = "ffprobe"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("max_upload_bytes", mode="before")
    @classmethod
    def empty_max_upload_bytes_uses_default(cls, value):
        if not os.getenv("MAX_UPLOAD_BYTES", "").strip() or (isinstance(value, str) and not value.strip()):
            return 524_288_000
        return value

    @field_validator("storage_root", mode="before")
    @classmethod
    def blank_storage_root_uses_writable_runtime_path(cls, value):
        if os.getenv("VERCEL") == "1" and not os.getenv("STORAGE_ROOT", "").strip():
            return Path("/tmp/supervideoeditorai")
        if isinstance(value, str) and not value.strip():
            return Path("./storage")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def uploads_dir(self) -> Path:
        return self.storage_root / "uploads"

    @property
    def projects_dir(self) -> Path:
        return self.storage_root / "projects"

    @property
    def outputs_dir(self) -> Path:
        return self.storage_root / "outputs"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    try:
        settings.storage_root.mkdir(parents=True, exist_ok=True)
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        settings.projects_dir.mkdir(parents=True, exist_ok=True)
        settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        if settings.storage_root == Path("/tmp/supervideoeditorai"):
            raise
        settings.storage_root = Path("/tmp/supervideoeditorai")
        settings.storage_root.mkdir(parents=True, exist_ok=True)
        settings.uploads_dir.mkdir(parents=True, exist_ok=True)
        settings.projects_dir.mkdir(parents=True, exist_ok=True)
        settings.outputs_dir.mkdir(parents=True, exist_ok=True)
    return settings
