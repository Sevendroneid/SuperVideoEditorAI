import json
from datetime import datetime, timezone
from pathlib import Path

from .models import JobRecord, JobStatus


class JobStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def create(self, job_id: str) -> JobRecord:
        record = JobRecord.new(job_id)
        self.save(record)
        return record

    def save(self, record: JobRecord) -> None:
        record.updated_at = datetime.now(timezone.utc)
        tmp = self._path(record.id).with_suffix(".tmp")
        tmp.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(self._path(record.id))

    def get(self, job_id: str) -> JobRecord | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        try:
            return JobRecord.model_validate(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            return None

    def update(self, job_id: str, **changes) -> JobRecord:
        record = self.get(job_id)
        if record is None:
            raise KeyError(job_id)
        for key, value in changes.items():
            setattr(record, key, value)
        self.save(record)
        return record
