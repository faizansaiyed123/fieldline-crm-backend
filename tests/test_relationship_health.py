from datetime import UTC, datetime, timedelta
from importlib.util import find_spec

import pytest

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import (
    Activity,
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


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_relationship_health_is_explainable(client, db_session) -> None:
    organization = Organization(name="Health Org", slug=f"health-{id(db_session)}")
    user = User(
        email=f"health-{id(db_session)}@example.com",
        full_name="Health User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(
        organization=organization,
        user=user,
        role=MembershipRole.OWNER,
    )
    db_session.add_all([organization, user, membership])
    db_session.flush()

    contact = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Ada",
        last_name="Lovelace",
        lifecycle="customer",
    )
    stage = PipelineStage(
        organization_id=organization.id,
        name="Proposal",
        order_index=30,
        win_probability=0.5,
    )
    db_session.add_all([contact, stage])
    db_session.flush()

    activity = Activity(
        organization_id=organization.id,
        actor_user_id=user.id,
        contact_id=contact.id,
        activity_type="call",
        title="Renewal call",
        occurred_at=datetime.now(UTC) - timedelta(days=2),
        activity_metadata={},
    )
    opportunity = Opportunity(
        organization_id=organization.id,
        owner_user_id=user.id,
        contact_id=contact.id,
        stage_id=stage.id,
        name="Renewal",
        status="open",
    )
    overdue = Task(
        organization_id=organization.id,
        created_by_user_id=user.id,
        contact_id=contact.id,
        title="Follow up",
        due_at=datetime.now(UTC) - timedelta(days=1),
    )
    db_session.add_all([activity, opportunity, overdue])
    db_session.flush()

    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/organizations/{organization.id}/contacts/{contact.id}/relationship-health",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["score"] >= 50
    assert body["band"] in {"healthy", "warming", "at_risk", "dormant"}
    assert body["activity_count_30d"] == 1
    assert body["open_opportunity_count"] == 1
    assert body["overdue_task_count"] == 1
    codes = {item["code"] for item in body["evidence"]}
    assert {"active_3d", "engagement_30d", "open_opportunities", "overdue_tasks"} <= codes


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_relationship_health_is_tenant_scoped(client, db_session) -> None:
    organization = Organization(name="Health One", slug=f"health-one-{id(db_session)}")
    user = User(
        email=f"health-one-{id(db_session)}@example.com",
        full_name="One User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(
        organization=organization,
        user=user,
        role=MembershipRole.OWNER,
    )
    other = Organization(name="Health Two", slug=f"health-two-{id(client)}")
    other_user = User(
        email=f"health-two-{id(client)}@example.com",
        full_name="Two User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    other_membership = Membership(
        organization=other,
        user=other_user,
        role=MembershipRole.OWNER,
    )
    db_session.add_all([organization, user, membership, other, other_user, other_membership])
    db_session.flush()

    foreign_contact = Contact(
        organization_id=other.id,
        owner_user_id=other_user.id,
        first_name="Foreign",
        last_name="Contact",
        lifecycle="customer",
    )
    db_session.add(foreign_contact)
    db_session.flush()

    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/organizations/{organization.id}/contacts/{foreign_contact.id}/relationship-health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
