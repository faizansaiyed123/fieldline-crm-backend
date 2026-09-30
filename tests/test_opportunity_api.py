from importlib.util import find_spec

import pytest

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import Company, Membership, MembershipRole, Organization, PipelineStage, User

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_opportunity_workflow(client, db_session) -> None:
    organization = Organization(name="Sales Org", slug=f"sales-{id(db_session)}")
    user = User(
        email=f"sales-{id(db_session)}@example.com",
        full_name="Sales User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(
        organization=organization,
        user=user,
        role=MembershipRole.OWNER,
    )
    db_session.add_all([organization, user, membership])
    db_session.flush()

    stage = PipelineStage(
        organization=organization,
        name="Proposal",
        order_index=30,
        win_probability=0.5,
    )
    company = Company(
        organization_id=organization.id,
        owner_user_id=user.id,
        name="Sales Company",
    )
    db_session.add_all([stage, company])
    db_session.flush()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/organizations/{organization.id}/opportunities"

    created = client.post(
        base,
        json={
            "name": "CRM Expansion",
            "stage_id": str(stage.id),
            "company_id": str(company.id),
            "amount": "12000.00",
        },
        headers=headers,
    )
    assert created.status_code == 201
    body = created.json()
    assert body["amount"] == "12000.00"
    opportunity_id = body["id"]

    updated = client.patch(
        f"{base}/{opportunity_id}",
        json={"status": "lost"},
        headers=headers,
    )
    assert updated.status_code == 400

    updated = client.patch(
        f"{base}/{opportunity_id}",
        json={"status": "lost", "lost_reason": "Budget deferred"},
        headers=headers,
    )
    assert updated.status_code == 400

    closed_stage = PipelineStage(
        organization_id=organization.id,
        name="Closed Lost",
        order_index=60,
        win_probability=0,
        is_closed=True,
        is_won=False,
    )
    db_session.add(closed_stage)
    db_session.flush()

    updated = client.patch(
        f"{base}/{opportunity_id}",
        json={"stage_id": str(closed_stage.id), "lost_reason": "Budget deferred"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "lost"

    filtered = client.get(
        f"{base}?status=lost",
        headers=headers,
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_opportunity_rejects_cross_tenant_company(client, db_session) -> None:
    org = Organization(name="One", slug=f"one-{id(db_session)}")
    user = User(
        email=f"one-{id(db_session)}@example.com",
        full_name="One User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    member = Membership(organization=org, user=user, role=MembershipRole.OWNER)
    db_session.add_all([org, user, member])
    db_session.flush()

    other = Organization(name="Two", slug=f"two-{id(db_session)}")
    other_user = User(
        email=f"two-{id(db_session)}@example.com",
        full_name="Two User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    other_member = Membership(
        organization=other,
        user=other_user,
        role=MembershipRole.OWNER,
    )
    other_stage = PipelineStage(
        organization=other,
        name="New",
        order_index=10,
    )
    other_company = Company(
        organization_id=other.id,
        owner_user_id=other_user.id,
        name="Other Company",
    )
    db_session.add_all([other, other_user, other_member])
    db_session.flush()

    other_stage = PipelineStage(
        organization_id=other.id,
        name="New",
        order_index=10,
    )
    other_company = Company(
        organization_id=other.id,
        owner_user_id=other_user.id,
        name="Other Company",
    )
    db_session.add_all([other_stage, other_company])
    db_session.flush()

    token = create_access_token(user.id)
    response = client.post(
        f"/api/v1/organizations/{org.id}/opportunities",
        json={
            "name": "Cross Tenant",
            "stage_id": str(other_stage.id),
            "company_id": str(other_company.id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
