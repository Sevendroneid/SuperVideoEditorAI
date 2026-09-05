from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_dashboard_root_is_served():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "SuperVideoEditorAI" in response.text


def test_dashboard_assets_are_served():
    script = client.get("/app.js")
    styles = client.get("/styles.css")
    assert script.status_code == 200
    assert script.headers["content-type"].startswith("application/javascript")
    assert "Create Project" in client.get("/").text
    assert styles.status_code == 200
    assert styles.headers["content-type"].startswith("text/css")


def test_unknown_project_is_rejected():
    response = client.post("/api/v1/projects/not-a-real-project/analyze")
    assert response.status_code == 404


def test_invalid_project_id_is_rejected_before_filesystem_access():
    response = client.get("/api/v1/projects/../../outside/analysis")
    assert response.status_code in {400, 404}


def test_invalid_job_id_is_rejected():
    response = client.get("/api/v1/jobs/../../outside")
    assert response.status_code in {400, 404}


def test_output_endpoint_does_not_accept_path_traversal():
    response = client.get("/api/v1/projects/../../outside/output")
    assert response.status_code in {400, 404}
