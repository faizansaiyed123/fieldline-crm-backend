from importlib.util import find_spec

import pytest

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import Membership, MembershipRole, Organization, User

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


def _identity(db_session):
    suffix = str(id(db_session))
    organization = Organization(name="Boundary Test Org", slug=f"boundary-{suffix}")
    user = User(
        email=f"boundary-{suffix}@example.com",
        full_name="Boundary Test User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(
        organization=organization,
        user=user,
        role=MembershipRole.OWNER,
    )
    db_session.add_all([organization, user, membership])
    db_session.flush()
    return organization, {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_company_name_accepts_minimum_and_maximum_lengths(client, db_session) -> None:
    organization, headers = _identity(db_session)
    base = f"/api/v1/organizations/{organization.id}/companies"

    for name in ("AB", "C" * 200):
        response = client.post(base, json={"name": name}, headers=headers)
        assert response.status_code == 201
        assert response.json()["name"] == name


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
@pytest.mark.parametrize(
    "payload",
    [
        {"name": "A"},
        {"name": "   "},
        {"name": "C" * 201},
        {"name": "Valid Company", "website": "not a URL"},
        {"name": "Valid Company", "phone": "1" * 41},
    ],
)
def test_company_create_rejects_invalid_field_boundaries(client, db_session, payload) -> None:
    organization, headers = _identity(db_session)
    base = f"/api/v1/organizations/{organization.id}/companies"

    response = client.post(base, json=payload, headers=headers)

    assert response.status_code == 422
    listed = client.get(base, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_contact_create_accepts_minimum_names_and_maximum_optional_lengths(
    client, db_session
) -> None:
    organization, headers = _identity(db_session)
    base = f"/api/v1/organizations/{organization.id}/contacts"
    payload = {
        "first_name": "A",
        "last_name": "B" * 100,
        "phone": "1" * 40,
        "job_title": "T" * 160,
        "lifecycle": "churned",
    }

    response = client.post(base, json=payload, headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["first_name"] == "A"
    assert body["last_name"] == "B" * 100
    assert body["phone"] == "1" * 40
    assert body["job_title"] == "T" * 160
    assert body["lifecycle"] == "churned"


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
@pytest.mark.parametrize(
    "payload",
    [
        {"first_name": "", "last_name": "Valid"},
        {"first_name": "  ", "last_name": "Valid"},
        {"first_name": "A" * 101, "last_name": "Valid"},
        {"first_name": "Valid", "last_name": "B" * 101},
        {"first_name": "Valid", "last_name": "Person", "email": "not-an-email"},
        {"first_name": "Valid", "last_name": "Person", "lifecycle": "qualified"},
        {"first_name": "Valid", "last_name": "Person", "phone": "1" * 41},
        {"first_name": "Valid", "last_name": "Person", "job_title": "T" * 161},
    ],
)
def test_contact_create_rejects_invalid_field_boundaries(client, db_session, payload) -> None:
    organization, headers = _identity(db_session)
    base = f"/api/v1/organizations/{organization.id}/contacts"

    response = client.post(base, json=payload, headers=headers)

    assert response.status_code == 422
    listed = client.get(base, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
@pytest.mark.parametrize(
    ("resource", "query"),
    [
        ("companies", "page=0"),
        ("companies", "page_size=0"),
        ("companies", "page_size=101"),
        ("companies", "q="),
        ("companies", f"q={'x' * 101}"),
        ("contacts", "page=0"),
        ("contacts", "page_size=0"),
        ("contacts", "page_size=101"),
        ("contacts", "q="),
        ("contacts", f"q={'x' * 101}"),
    ],
)
def test_directory_endpoints_reject_invalid_query_boundaries(
    client, db_session, resource, query
) -> None:
    organization, headers = _identity(db_session)
    response = client.get(
        f"/api/v1/organizations/{organization.id}/{resource}?{query}",
        headers=headers,
    )

    assert response.status_code == 422
