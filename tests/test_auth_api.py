from importlib.util import find_spec

import pytest
from sqlalchemy import select

from app.models import AuthSession, PipelineStage

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_signup_creates_identity_pipeline_and_session(client, db_session) -> None:
    response = client.post(
        "/api/v1/auth/signup",
        json={
            "organization_name": "Auth Test",
            "full_name": "Auth User",
            "email": "auth-user@example.com",
            "password": "Correct Horse Battery Staple",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["user"]["email"] == "auth-user@example.com"
    assert body["user"]["memberships"][0]["role"] == "owner"

    stages = db_session.scalars(select(PipelineStage)).all()
    assert [stage.name for stage in stages] == [
        "New",
        "Qualified",
        "Proposal",
        "Negotiation",
        "Closed Won",
        "Closed Lost",
    ]

    sessions = db_session.scalars(select(AuthSession)).all()
    assert len(sessions) == 1
    assert client.cookies.get("fieldline_refresh")
    assert client.cookies.get("fieldline_csrf")


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_refresh_rotates_session_and_requires_csrf(client) -> None:
    signup = client.post(
        "/api/v1/auth/signup",
        json={
            "organization_name": "Refresh Test",
            "full_name": "Refresh User",
            "email": "refresh-user@example.com",
            "password": "Correct Horse Battery Staple",
        },
    )
    assert signup.status_code == 201

    old_refresh = client.cookies.get("fieldline_refresh")
    old_csrf = client.cookies.get("fieldline_csrf")
    assert old_refresh and old_csrf

    missing_csrf = client.post("/api/v1/auth/refresh")
    assert missing_csrf.status_code == 403

    refreshed = client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": old_csrf},
    )
    assert refreshed.status_code == 200
    new_refresh = client.cookies.get("fieldline_refresh")
    assert new_refresh
    assert new_refresh != old_refresh

    client.cookies.set("fieldline_refresh", old_refresh)
    client.cookies.set("fieldline_csrf", old_csrf)
    reused = client.post(
        "/api/v1/auth/refresh",
        headers={"X-CSRF-Token": old_csrf},
    )
    assert reused.status_code == 401


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_successful_signup_does_not_consume_ip_failure_quota(client) -> None:
    for suffix in range(5):
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "organization_name": f"Quota Org {suffix}",
                "full_name": "Quota User",
                "email": f"quota-{suffix}@example.com",
                "password": "Correct Horse Battery Staple",
            },
        )
        assert response.status_code == 201
