from __future__ import annotations

import os
import uuid
from pathlib import Path
from urllib.parse import quote, urlparse

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
        timeout = kwargs.pop("timeout", 60.0)
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, f"{self.url}{path}", headers=headers, **kwargs)
            if response.is_error:
                detail = response.text[:1000]
                raise RuntimeError(f"Supabase {method} {path} failed with HTTP {response.status_code}: {detail}")
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
        self._request("POST", "/rest/v1/clips", json={"id": clip_id, "project_id": self._project_uuid(project_id), "original_filename": filename, "storage_path": storage_path, "bytes": size})
        return clip_id

    def get_project_clips(self, project_id: str) -> list[dict]:
        response = self._request("GET", "/rest/v1/clips", params={"project_id": f"eq.{self._project_uuid(project_id)}", "order": "created_at.asc"})
        return response.json()

    def create_job(self, project_id: str, job_id: str, kind: str) -> None:
        self._request("POST", "/rest/v1/jobs", json={"id": job_id, "project_id": self._project_uuid(project_id), "job_key": job_id, "kind": kind, "status": "queued", "progress": 0})

    def update_job(self, job_id: str, **changes) -> None:
        self._request("PATCH", "/rest/v1/jobs", params={"id": f"eq.{job_id}"}, json=changes)

    def get_job(self, job_id: str) -> dict | None:
        response = self._request("GET", "/rest/v1/jobs", params={"id": f"eq.{job_id}", "limit": 1})
        rows = response.json()
        return rows[0] if rows else None

    def get_active_job(self, project_id: str, kind: str) -> dict | None:
        project_uuid = self._project_uuid(project_id)
        response = self._request("GET", "/rest/v1/jobs", params={"project_id": f"eq.{project_uuid}", "kind": f"eq.{kind}", "status": "in.(queued,processing)", "order": "created_at.desc", "limit": 1})
        rows = response.json()
        return rows[0] if rows else None

    def create_signed_upload(self, storage_path: str) -> dict:
        encoded_path = quote(storage_path, safe="/")
        response = self._request("POST", f"/storage/v1/object/upload/sign/{self.bucket}/{encoded_path}", headers={"x-upsert": "true", "Content-Type": "application/json"}, json={})
        data = response.json()
        relative_url = data.get("url")
        if not relative_url:
            raise RuntimeError("Supabase did not return a signed upload URL")
        signed_url = f"{self.url}{relative_url}" if relative_url.startswith("/") else relative_url
        token = signed_url.split("token=", 1)[1] if "token=" in signed_url else ""
        if not token:
            raise RuntimeError("Supabase did not return a signed upload token")
        parsed = urlparse(self.url)
        project_host = parsed.hostname or ""
        if project_host.endswith(".supabase.co"):
            project_ref = project_host[:-len(".supabase.co")]
            resumable_endpoint = f"https://{project_ref}.storage.supabase.co/storage/v1/upload/resumable"
        else:
            resumable_endpoint = f"{self.url}/storage/v1/upload/resumable"
        return {"path": storage_path, "signed_url": signed_url, "token": token, "resumable_endpoint": resumable_endpoint}

    def storage_object_info(self, storage_path: str) -> dict:
        encoded_path = quote(storage_path, safe="/")
        response = self._request("HEAD", f"/storage/v1/object/info/{self.bucket}/{encoded_path}", timeout=60.0)
        return {"bytes": int(response.headers.get("content-length", "0")), "content_type": response.headers.get("content-type", "application/octet-stream")}

    def create_signed_download(self, storage_path: str, expires_in: int = 3600) -> str:
        encoded_path = quote(storage_path, safe="/")
        response = self._request("POST", f"/storage/v1/object/sign/{self.bucket}/{encoded_path}", headers={"Content-Type": "application/json"}, json={"expiresIn": expires_in})
        signed_url = response.json().get("signedURL")
        if not signed_url:
            raise RuntimeError("Supabase did not return a signed download URL")
        return f"{self.url}{signed_url}" if signed_url.startswith("/") else signed_url

    def upload_file(self, local_path: Path, storage_path: str, content_type: str = "application/octet-stream", upsert: bool = False) -> None:
        headers = {"Content-Type": content_type, "x-upsert": "true" if upsert else "false"}
        self._request("POST", f"/storage/v1/object/{self.bucket}/{storage_path}", content=local_path.read_bytes(), headers=headers, timeout=300.0)

    def download_file(self, storage_path: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with httpx.Client(timeout=300.0) as client:
            with client.stream("GET", f"{self.url}/storage/v1/object/{self.bucket}/{storage_path}", headers=self._headers()) as response:
                if response.is_error:
                    detail = response.read().decode("utf-8", errors="replace")[:1000]
                    raise RuntimeError(f"Supabase GET /storage/v1/object/{self.bucket}/{storage_path} failed with HTTP {response.status_code}: {detail}")
                with destination.open("wb") as output:
                    for chunk in response.iter_bytes(1024 * 1024):
                        output.write(chunk)
        return destination

    def create_artifact(self, project_id: str, artifact_type: str, storage_path: str, metadata: dict | None = None) -> None:
        project_uuid = self._project_uuid(project_id)
        payload = {"storage_path": storage_path, "metadata": metadata or {}}
        response = self._request("PATCH", "/rest/v1/project_artifacts", params={"project_id": f"eq.{project_uuid}", "artifact_type": f"eq.{artifact_type}"}, headers={"Prefer": "return=representation"}, json=payload)
        if response.json():
            return
        self._request("POST", "/rest/v1/project_artifacts", json={"project_id": project_uuid, "artifact_type": artifact_type, **payload})

    def get_artifacts(self, project_id: str, artifact_type: str | None = None) -> list[dict]:
        params = {"project_id": f"eq.{self._project_uuid(project_id)}", "order": "created_at.desc"}
        if artifact_type: params["artifact_type"] = f"eq.{artifact_type}"
        return self._request("GET", "/rest/v1/project_artifacts", params=params).json()
