from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class JobStatus(str, Enum):
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class ClipEvidence(BaseModel):
    path: str
    filename: str
    duration_seconds: float = Field(ge=0)
    width: int = Field(ge=0)
    height: int = Field(ge=0)
    fps: float = Field(ge=0)
    frame_count: int = Field(ge=0)
    score: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)


class TimelineItem(BaseModel):
    clip_path: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    role: Literal["establish", "action", "detail", "reveal", "resolution", "unknown"] = "unknown"

    @field_validator("end_seconds")
    @classmethod
    def end_after_start(cls, value: float, info):
        start = info.data.get("start_seconds")
        if start is not None and value <= start:
            raise ValueError("end_seconds must be greater than start_seconds")
        return value


class Timeline(BaseModel):
    version: int = 1
    items: list[TimelineItem]
    total_duration_seconds: float = Field(ge=0)


class JobRecord(BaseModel):
    id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    progress: int = Field(ge=0, le=100)
    message: str = ""
    result: dict | None = None
    error: str | None = None

    @classmethod
    def new(cls, job_id: str) -> "JobRecord":
        now = datetime.now(timezone.utc)
        return cls(id=job_id, status=JobStatus.queued, created_at=now, updated_at=now, progress=0)


def safe_filename(filename: str) -> str:
    candidate = Path(filename).name
    if not candidate or candidate in {".", ".."}:
        raise ValueError("Invalid filename")
    return candidate
