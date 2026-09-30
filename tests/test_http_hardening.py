from fastapi.testclient import TestClient

from app.main import app


def test_request_id_and_security_headers() -> None:
    client = TestClient(app)
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "test-request-123"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "test-request-123"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert response.headers["Permissions-Policy"] == "camera=(), microphone=(), geolocation=()"


def test_invalid_request_id_is_replaced() -> None:
    client = TestClient(app)
    response = client.get(
        "/api/v1/health",
        headers={"X-Request-ID": "invalid request id"},
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "invalid request id"
    assert len(response.headers["X-Request-ID"]) == 32
