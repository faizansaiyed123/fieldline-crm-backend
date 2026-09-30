from importlib.util import find_spec

import pytest

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import Company, Membership, MembershipRole, Organization, User

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


def _identity(db_session, *, slug: str, email: str):
    organization = Organization(name="Test Org", slug=slug)
    user = User(
        email=email,
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
def test_contact_crud_search_and_company_assignment(client, db_session) -> None:
    organization, user = _identity(
        db_session,
        slug=f"contact-{id(db_session)}",
        email=f"contact-{id(db_session)}@example.com",
    )
    company = Company(
        organization_id=organization.id,
        owner_user_id=user.id,
        name="Acme Consulting",
    )
    db_session.add(company)
    db_session.flush()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/organizations/{organization.id}/contacts"

    created = client.post(
        base,
        json={
            "first_name": " Ada ",
            "last_name": " Lovelace ",
            "email": "ADA@EXAMPLE.COM",
            "job_title": " Architect ",
            "company_id": str(company.id),
            "lifecycle": "prospect",
        },
        headers=headers,
    )
    assert created.status_code == 201
    contact = created.json()
    assert contact["first_name"] == "Ada"
    assert contact["last_name"] == "Lovelace"
    assert contact["email"] == "ada@example.com"
    assert contact["company_id"] == str(company.id)
    assert contact["lifecycle"] == "prospect"

    searched = client.get(
        f"{base}?q=lovelace&page=1&page_size=10",
        headers=headers,
    )
    assert searched.status_code == 200
    assert searched.json()["total"] == 1

    updated = client.patch(
        f"{base}/{contact['id']}",
        json={"lifecycle": "customer"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["lifecycle"] == "customer"


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_contact_rejects_company_from_another_organization(client, db_session) -> None:
    organization, user = _identity(
        db_session,
        slug=f"contact-a-{id(db_session)}",
        email=f"contact-a-{id(db_session)}@example.com",
    )
    other_org, other_user = _identity(
        db_session,
        slug=f"contact-b-{id(db_session)}",
        email=f"contact-b-{id(db_session)}@example.com",
    )
    company = Company(
        organization_id=other_org.id,
        owner_user_id=other_user.id,
        name="Other Company",
    )
    db_session.add(company)
    db_session.flush()

    token = create_access_token(user.id)
    response = client.post(
        f"/api/v1/organizations/{organization.id}/contacts",
        json={
            "first_name": "Grace",
            "last_name": "Hopper",
            "company_id": str(company.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
