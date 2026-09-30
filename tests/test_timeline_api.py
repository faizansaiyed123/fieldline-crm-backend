from datetime import UTC, datetime, timedelta
from importlib.util import find_spec

import pytest

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import (
    Activity,
    AuditEvent,
    Contact,
    Membership,
    MembershipRole,
    Organization,
    Task,
    User,
)

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_contact_timeline_is_sorted_and_cursor_paginated(client, db_session) -> None:
    organization = Organization(name="Timeline Org", slug=f"timeline-{id(db_session)}")
    user = User(
        email=f"timeline-{id(db_session)}@example.com",
        full_name="Timeline User",
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
        first_name="Timeline",
        last_name="Contact",
        email="timeline@example.com",
    )
    db_session.add(contact)
    db_session.flush()

    t1 = datetime.now(UTC) - timedelta(minutes=3)
    t2 = datetime.now(UTC) - timedelta(minutes=2)
    t3 = datetime.now(UTC) - timedelta(minutes=1)
    db_session.add_all(
        [
            Activity(
                organization_id=organization.id,
                actor_user_id=user.id,
                contact_id=contact.id,
                activity_type="note",
                title="Called customer",
                body="Discussed renewal",
                occurred_at=t1,
                activity_metadata={},
            ),
            Task(
                organization_id=organization.id,
                created_by_user_id=user.id,
                contact_id=contact.id,
                title="Send proposal",
                due_at=t2,
            ),
            AuditEvent(
                organization_id=organization.id,
                actor_user_id=user.id,
                entity_type="contact",
                entity_id=contact.id,
                action="updated",
                summary="Lifecycle changed",
                created_at=t3,
            ),
        ]
    )
    db_session.flush()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    url = f"/api/v1/organizations/{organization.id}/contacts/{contact.id}/timeline"

    first = client.get(f"{url}?limit=2", headers=headers)
    assert first.status_code == 200
    body = first.json()
    assert [item["kind"] for item in body["items"]] == ["audit", "task"]
    assert body["next_before"]
    assert body["next_before_id"]

    second = client.get(
        url,
        params={
            "limit": 2,
            "before": body["next_before"],
            "before_id": body["next_before_id"],
        },
        headers=headers,
    )
    assert second.status_code == 200
    assert [item["kind"] for item in second.json()["items"]] == ["activity"]
    assert second.json()["next_before"] is None


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_contact_timeline_enforces_tenant_scope(client, db_session) -> None:
    org = Organization(name="Timeline One", slug=f"timeline-one-{id(db_session)}")
    user = User(
        email=f"timeline-one-{id(db_session)}@example.com",
        full_name="One User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(
        organization=org,
        user=user,
        role=MembershipRole.OWNER,
    )
    other = Organization(name="Timeline Two", slug=f"timeline-two-{id(client)}")
    other_user = User(
        email=f"timeline-two-{id(client)}@example.com",
        full_name="Two User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    other_member = Membership(
        organization=other,
        user=other_user,
        role=MembershipRole.OWNER,
    )
    db_session.add_all([other, other_user, other_member])
    db_session.flush()

    contact = Contact(
        organization_id=other.id,
        owner_user_id=other_user.id,
        first_name="Other",
        last_name="Contact",
    )
    db_session.add_all([org, user, membership, contact])
    db_session.flush()

    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/organizations/{org.id}/contacts/{contact.id}/timeline",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404
