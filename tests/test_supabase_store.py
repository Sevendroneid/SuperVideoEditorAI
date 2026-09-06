from pathlib import Path

import pytest

from app.supabase_store import SupabaseStore


def test_supabase_store_is_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    store = SupabaseStore()
    assert store.enabled is False
    with pytest.raises(RuntimeError, match="Supabase storage is not configured"):
        store._headers()


def test_supabase_store_headers_are_server_side(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-test-key")
    store = SupabaseStore()
    assert store.enabled is True
    assert store._headers() == {
        "apikey": "service-role-test-key",
        "Authorization": "Bearer service-role-test-key",
    }


def test_storage_path_is_not_derived_from_local_absolute_paths():
    store = SupabaseStore("https://example.supabase.co", "key")
    local = Path("/tmp/supervideoeditorai/project/clip.mp4")
    assert local.name == "clip.mp4"
    assert store.bucket == "supervideo"


def test_create_signed_upload_decodes_percent_encoded_tus_token(monkeypatch):
    store = SupabaseStore("https://lykhuijrmlgassuajbpi.supabase.co", "key")
    raw_token = "header.payload.signature"
    encoded_token = "header%2Epayload%2Esignature"

    class Response:
        def json(self):
            return {"url": f"/object/upload/sign/supervideo/project/clip.mp4?token={encoded_token}"}

    monkeypatch.setattr(store, "_request", lambda *args, **kwargs: Response())
    session = store.create_signed_upload("project/clip.mp4")

    assert session["token"] == raw_token
    assert session["signed_url"] == "https://lykhuijrmlgassuajbpi.supabase.co/storage/v1/object/upload/sign/supervideo/project/clip.mp4?token=header%2Epayload%2Esignature"
    assert session["resumable_endpoint"] == "https://lykhuijrmlgassuajbpi.storage.supabase.co/storage/v1/upload/resumable"


def test_create_signed_upload_accepts_storage_prefixed_url(monkeypatch):
    store = SupabaseStore("https://example.supabase.co", "key")

    class Response:
        def json(self):
            return {"url": "/storage/v1/object/upload/sign/supervideo/project/clip.mp4?token=header.payload.signature"}

    monkeypatch.setattr(store, "_request", lambda *args, **kwargs: Response())
    session = store.create_signed_upload("project/clip.mp4")

    assert session["signed_url"].startswith("https://example.supabase.co/storage/v1/object/upload/sign/")


def test_create_signed_upload_prefers_explicit_token(monkeypatch):
    store = SupabaseStore("https://example.supabase.co", "key")
    raw_token = "header.payload.signature"

    class Response:
        def json(self):
            return {
                "url": "/object/upload/sign/supervideo/project/clip.mp4?token=stale",
                "token": raw_token,
            }

    monkeypatch.setattr(store, "_request", lambda *args, **kwargs: Response())
    session = store.create_signed_upload("project/clip.mp4")

    assert session["token"] == raw_token
    assert session["signed_url"].startswith("https://example.supabase.co/storage/v1/object/upload/sign/")
    assert session["resumable_endpoint"] == "https://example.storage.supabase.co/storage/v1/upload/resumable"


def test_storage_object_info_reads_size_from_supabase_metadata(monkeypatch):
    store = SupabaseStore("https://example.supabase.co", "key")

    class Response:
        def json(self):
            return {"size": 32373, "contentType": "video/mp4"}

    calls = []
    monkeypatch.setattr(store, "_request", lambda *args, **kwargs: (calls.append((args, kwargs)) or Response()))
    info = store.storage_object_info("project/clip.mp4")

    assert info == {"bytes": 32373, "content_type": "video/mp4"}
    assert calls[0][0][0] == "GET"
    assert calls[0][0][1] == "/storage/v1/object/info/supervideo/project/clip.mp4"
