from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "fieldline-api"}


def test_root_hidden_from_openapi() -> None:
    schema = client.get("/api/v1/openapi.json").json()
    assert "/" not in schema["paths"]
    assert "/api/v1/health" in schema["paths"]
    assert "/api/v1/ready" in schema["paths"]
