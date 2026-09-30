from importlib.util import find_spec

import pytest
from sqlalchemy import func, select

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import AuditEvent, Membership, MembershipRole, Organization, User

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


def _create_identity(db_session):
    organization = Organization(
        name="Acme Test",
        slug=f"acme-{Organization.__table__.name}-{id(db_session)}",
    )
    user = User(
        email=f"user-{id(db_session)}@example.com",
        full_name="Test User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(
        organization=organization,
        user=user,
        role=MembershipRole.OWNER,
    )
    db_session.add_all([organization, user, membership])
    db_session.flush()
    return organization, user


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_company_crud_search_archive_and_audit(client, db_session) -> None:
    organization, user = _create_identity(db_session)
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/organizations/{organization.id}/companies"

    created = client.post(
        base,
        json={
            "name": "Acme Consulting",
            "website": "https://acme.example",
            "phone": "123-456",
        },
        headers=headers,
    )
    assert created.status_code == 201
    company = created.json()
    assert company["name"] == "Acme Consulting"
    company_id = company["id"]

    duplicate = client.post(
        base,
        json={"name": "acme consulting"},
        headers=headers,
    )
    assert duplicate.status_code == 409

    searched = client.get(
        f"{base}?q=consulting&page=1&page_size=10",
        headers=headers,
    )
    assert searched.status_code == 200
    assert searched.json()["total"] == 1

    updated = client.patch(
        f"{base}/{company_id}",
        json={"phone": "+91 99999 99999"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["phone"] == "+91 99999 99999"

    audit_count = db_session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.entity_id == company_id)
    )
    assert audit_count == 2

    archived = client.delete(f"{base}/{company_id}", headers=headers)
    assert archived.status_code == 204

    listed = client.get(base, headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 0


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_company_endpoint_enforces_tenant_membership(client, db_session) -> None:
    organization, user = _create_identity(db_session)
    other = Organization(name="Other", slug=f"other-{id(client)}")
    db_session.add(other)
    db_session.flush()

    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/organizations/{other.id}/companies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
