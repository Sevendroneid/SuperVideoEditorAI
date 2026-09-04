from fastapi.testclient import TestClient

from app.main import app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unknown_project_is_rejected():
    response = TestClient(app).post("/api/v1/projects/not-a-real-project/analyze")
    assert response.status_code == 404
