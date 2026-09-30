from datetime import UTC, datetime, timedelta
from importlib.util import find_spec

import pytest

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import (
    Contact,
    Membership,
    MembershipRole,
    Opportunity,
    Organization,
    PipelineStage,
    Task,
    User,
)

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


def _identity(db_session):
    organization = Organization(name="Attention Org", slug=f"attention-{id(db_session)}")
    user = User(
        email=f"attention-{id(db_session)}@example.com",
        full_name="Attention User",
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
def test_attention_queue_explains_overdue_and_stale_signals(client, db_session) -> None:
    organization, user = _identity(db_session)
    stage = PipelineStage(
        organization_id=organization.id,
        name="New",
        order_index=10,
    )
    db_session.add(stage)
    db_session.flush()

    old_opportunity = Opportunity(
        organization_id=organization.id,
        owner_user_id=user.id,
        stage_id=stage.id,
        name="Renewal Deal",
        status="open",
        expected_close_date=(datetime.now(UTC) - timedelta(days=2)).date(),
    )
    contact = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Ada",
        last_name="Lovelace",
        lifecycle="lead",
        created_at=datetime.now(UTC) - timedelta(days=30),
    )
    fresh_contact = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Fresh",
        last_name="Lead",
        lifecycle="lead",
        created_at=datetime.now(UTC) - timedelta(days=1),
    )
    overdue_task = Task(
        organization_id=organization.id,
        created_by_user_id=user.id,
        title="Follow up",
        due_at=datetime.now(UTC) - timedelta(hours=2),
    )
    db_session.add_all([old_opportunity, contact, fresh_contact, overdue_task])
    db_session.flush()

    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/organizations/{organization.id}/attention?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert items[0]["entity_type"] == "task"
    assert items[0]["priority"] == 95
    assert "overdue" in items[0]["reason"].lower()
    assert any(
        item["entity_id"] == str(old_opportunity.id) and item["priority"] == 90
        for item in items
    )
    assert any(
        item["entity_id"] == str(contact.id) and item["priority"] == 70
        for item in items
    )
    assert all(item["entity_id"] != str(fresh_contact.id) for item in items)


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_attention_queue_is_tenant_scoped(client, db_session) -> None:
    organization, user = _identity(db_session)
    other = Organization(name="Other", slug=f"other-attention-{id(client)}")
    other_user = User(
        email=f"other-attention-{id(client)}@example.com",
        full_name="Other User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    other_member = Membership(
        organization=other,
        user=other_user,
        role=MembershipRole.OWNER,
    )
    db_session.add_all([other, other_user, other_member])
    db_session.flush()

    foreign_task = Task(
        organization_id=other.id,
        created_by_user_id=other_user.id,
        title="Foreign overdue",
        due_at=datetime.now(UTC) - timedelta(hours=4),
    )
    db_session.add(foreign_task)
    db_session.flush()

    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/organizations/{organization.id}/attention",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert all(
        item["entity_id"] != str(foreign_task.id)
        for item in response.json()["items"]
    )


def test_attention_priority_order_contract() -> None:
    assert 95 > 90 > 70
