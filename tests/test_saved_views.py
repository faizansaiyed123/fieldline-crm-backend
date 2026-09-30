from importlib.util import find_spec

import pytest

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.db.base import Base
from app.models import Contact, Membership, MembershipRole, Organization, User

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


def _identity(db_session, *, role: MembershipRole = MembershipRole.OWNER):
    organization = Organization(name="Views Org", slug=f"views-{id(db_session)}")
    user = User(
        email=f"views-{id(db_session)}@example.com",
        full_name="Views User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(organization=organization, user=user, role=role)
    db_session.add_all([organization, user, membership])
    db_session.flush()
    return organization, user


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_private_view_filters_contacts_and_shared_view_is_visible(client, db_session) -> None:
    organization, user = _identity(db_session)
    other_user = User(
        email=f"views-other-{id(client)}@example.com",
        full_name="Other User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    other_membership = Membership(
        organization_id=organization.id,
        user=other_user,
        role=MembershipRole.MEMBER,
    )
    db_session.add_all([other_user, other_membership])
    db_session.flush()

    contacts = [
        Contact(
            organization_id=organization.id,
            owner_user_id=user.id,
            first_name="Ada",
            last_name="Lovelace",
            email="ada@example.com",
            lifecycle="prospect",
        ),
        Contact(
            organization_id=organization.id,
            owner_user_id=user.id,
            first_name="Grace",
            last_name="Hopper",
            lifecycle="prospect",
        ),
        Contact(
            organization_id=organization.id,
            owner_user_id=user.id,
            first_name="Alan",
            last_name="Turing",
            email="alan@example.com",
            lifecycle="customer",
        ),
    ]
    db_session.add_all(contacts)
    db_session.flush()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    base = f"/api/v1/organizations/{organization.id}/saved-views"

    private = client.post(
        base,
        json={
            "name": "Prospects with email",
            "shared": False,
            "definition": {"lifecycle": ["prospect"], "has_email": True, "sort": "name_asc"},
        },
        headers=headers,
    )
    assert private.status_code == 201
    private_id = private.json()["id"]

    executed = client.get(f"{base}/{private_id}/execute", headers=headers)
    assert executed.status_code == 200
    assert [item["first_name"] for item in executed.json()["items"]] == ["Ada"]

    shared = client.post(
        base,
        json={
            "name": "All prospects",
            "shared": True,
            "definition": {"lifecycle": ["prospect"]},
        },
        headers=headers,
    )
    assert shared.status_code == 201
    shared_id = shared.json()["id"]

    other_token = create_access_token(other_user.id)
    other_headers = {"Authorization": f"Bearer {other_token}"}
    visible = client.get(f"{base}/{shared_id}", headers=other_headers)
    assert visible.status_code == 200


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_private_view_is_not_visible_cross_user_and_member_cannot_share(client, db_session) -> None:
    organization, owner = _identity(db_session)
    member = User(
        email=f"views-member-{id(client)}@example.com",
        full_name="Member User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    db_session.add(member)
    db_session.flush()
    member_link = Membership(
        organization_id=organization.id,
        user_id=member.id,
        role=MembershipRole.MEMBER,
    )
    db_session.add(member_link)
    db_session.flush()

    owner_token = create_access_token(owner.id)
    created = client.post(
        f"/api/v1/organizations/{organization.id}/saved-views",
        json={
            "name": "Owner Private",
            "shared": False,
            "definition": {"query": "Ada"},
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert created.status_code == 201
    view_id = created.json()["id"]

    member_token = create_access_token(member.id)
    hidden = client.get(
        f"/api/v1/organizations/{organization.id}/saved-views/{view_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert hidden.status_code == 404

    blocked = client.post(
        f"/api/v1/organizations/{organization.id}/saved-views",
        json={
            "name": "Member Shared",
            "shared": True,
            "definition": {"query": "Ada"},
        },
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert blocked.status_code == 403


def test_saved_view_model_is_registered() -> None:
    assert "saved_views" in Base.metadata.tables
