from app.jobs import JobStore
from app.models import JobStatus


def test_job_store_round_trip(tmp_path):
    store = JobStore(tmp_path)
    created = store.create("job-1")
    assert created.status == JobStatus.queued
    updated = store.update("job-1", status=JobStatus.processing, progress=50, message="working")
    loaded = store.get("job-1")
    assert loaded is not None
    assert loaded.status == JobStatus.processing
    assert updated.progress == 50
    assert loaded.message == "working"
