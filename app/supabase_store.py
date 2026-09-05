from __future__ import annotations

import os
import uuid
from pathlib import Path

import httpx


class SupabaseStore:
    """Server-side REST adapter for Supabase Postgres and Storage."""

    def __init__(self, url: str | None = None, key: str | None = None, bucket: str = "supervideo") -> None:
        self.url = (url or os.getenv("SUPABASE_URL", "")).rstrip("/")
        self.key = key or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
        self.bucket = bucket

    @property
    def enabled(self) -> bool:
        return bool(self.url and self.key)

    def _headers(self) -> dict[str, str]:
        if not self.enabled:
            raise RuntimeError("Supabase storage is not configured")
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        extra_headers = kwargs.pop("headers", {})
        headers = {**self._headers(), **extra_headers}
        with httpx.Client(timeout=60.0) as client:
            response = client.request(method, f"{self.url}{path}", headers=headers, **kwargs)
            response.raise_for_status()
            return response

    def create_project(self, project_id: str) -> None:
        self._request("POST", "/rest/v1/projects", json={"project_key": project_id})

    def get_project(self, project_id: str) -> dict | None:
        response = self._request("GET", "/rest/v1/projects", params={"project_key": f"eq.{project_id}", "limit": 1})
        rows = response.json()
        return rows[0] if rows else None

    def _project_uuid(self, project_id: str) -> str:
        project = self.get_project(project_id)
        if not project or not project.get("id"):
            raise RuntimeError(f"Project not found in persistent storage: {project_id}")
        return str(project["id"])

    def create_clip(self, project_id: str, filename: str, storage_path: str, size: int) -> str:
        clip_id = str(uuid.uuid4())
        self._request("POST", "/rest/v1/clips", json={
            "id": clip_id, "project_id": self._project_uuid(project_id), "original_filename": filename,
            "storage_path": storage_path, "bytes": size,
        })
        return clip_id

    def get_project_clips(self, project_id: str) -> list[dict]:
        response = self._request("GET", "/rest/v1/clips", params={
            "project_id": f"eq.{self._project_uuid(project_id)}", "order": "created_at.asc"
        })
        return response.json()

    def create_job(self, project_id: str, job_id: str, kind: str) -> None:
        self._request("POST", "/rest/v1/jobs", json={
            "id": job_id, "project_id": self._project_uuid(project_id), "job_key": job_id,
            "kind": kind, "status": "queued", "progress": 0,
        })

    def update_job(self, job_id: str, **changes) -> None:
        self._request("PATCH", "/rest/v1/jobs", params={"id": f"eq.{job_id}"}, json=changes)

    def get_job(self, job_id: str) -> dict | None:
        response = self._request("GET", "/rest/v1/jobs", params={"id": f"eq.{job_id}", "limit": 1})
        rows = response.json()
        return rows[0] if rows else None

    def upload_file(self, local_path: Path, storage_path: str, content_type: str = "application/octet-stream", upsert: bool = False) -> None:
        self._request(
            "POST", f"/storage/v1/object/{self.bucket}/{storage_path}",
            content=local_path.read_bytes(),
            headers={"Content-Type": content_type, "x-upsert": "true" if upsert else "false"},
        )

    def download_file(self, storage_path: str, destination: Path) -> Path:
        response = self._request("GET", f"/storage/v1/object/{self.bucket}/{storage_path}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
        return destination

    def create_artifact(self, project_id: str, artifact_type: str, storage_path: str, metadata: dict | None = None) -> None:
        self._request("POST", "/rest/v1/project_artifacts", json={
            "project_id": self._project_uuid(project_id),
            "artifact_type": artifact_type,
            "storage_path": storage_path,
            "metadata": metadata or {},
        })

    def get_artifacts(self, project_id: str, artifact_type: str | None = None) -> list[dict]:
        params = {"project_id": f"eq.{self._project_uuid(project_id)}", "order": "created_at.desc"}
        if artifact_type:
            params["artifact_type"] = f"eq.{artifact_type}"
        return self._request("GET", "/rest/v1/project_artifacts", params=params).json()
