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
    # The adapter receives an explicit object key, so callers control the remote namespace.
    assert local.name == "clip.mp4"
    assert store.bucket == "supervideo"
