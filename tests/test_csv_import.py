import io
from importlib.util import find_spec

import pytest
from sqlalchemy import func, select

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import Contact, ImportJob, Membership, MembershipRole, Organization, User
from app.services.imports import MAX_FILE_SIZE, _parse_csv

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


def _identity(db_session, role=MembershipRole.OWNER):
    organization = Organization(name="Import Org", slug=f"import-{id(db_session)}")
    user = User(
        email=f"import-{id(db_session)}@example.com",
        full_name="Import User",
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
def test_contact_import_preview_dry_run_and_commit(client, db_session) -> None:
    organization, user = _identity(db_session)
    existing = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Existing",
        last_name="User",
        email="existing@example.com",
    )
    db_session.add(existing)
    db_session.flush()

    csv_content = (
        "first_name,last_name,email,phone,job_title,lifecycle\n"
        "Ada,Lovelace,ada@example.com,12345,Engineer,prospect\n"
        "Grace,Hopper,existing@example.com,67890,Admiral,lead\n"
        "Bad,,bad@example.com,99999,Engineer,lead\n"
    )
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    files = {"file": ("contacts.csv", io.BytesIO(csv_content.encode()), "text/csv")}

    preview = client.post(
        f"/api/v1/organizations/{organization.id}/imports/contacts/preview",
        files=files,
        headers=headers,
    )
    assert preview.status_code == 201
    body = preview.json()
    assert body["total_rows"] == 3
    assert body["valid_rows"] == 1
    assert body["invalid_rows"] == 2
    assert len(body["errors"]) == 2
    job_id = body["id"]

    dry_run = client.post(
        f"/api/v1/organizations/{organization.id}/imports/{job_id}/commit",
        json={"dry_run": True},
        headers=headers,
    )
    assert dry_run.status_code == 409

    job = db_session.scalar(select(ImportJob).where(ImportJob.id == job_id))
    assert job.status == "preview_ready"
    assert db_session.scalar(
        select(func.count()).select_from(Contact).where(Contact.organization_id == organization.id)
    ) == 1

    valid_csv = (
        "first_name,last_name,email\n"
        "Ada,Lovelace,ada@example.com\n"
    )
    preview2 = client.post(
        f"/api/v1/organizations/{organization.id}/imports/contacts/preview",
        files={"file": ("valid.csv", io.BytesIO(valid_csv.encode()), "text/csv")},
        headers=headers,
    )
    assert preview2.status_code == 201
    job2 = preview2.json()["id"]

    dry_run2 = client.post(
        f"/api/v1/organizations/{organization.id}/imports/{job2}/commit",
        json={"dry_run": True},
        headers=headers,
    )
    assert dry_run2.status_code == 200
    assert dry_run2.json()["would_create"] == 1
    assert db_session.scalar(
        select(func.count()).select_from(Contact).where(Contact.email == "ada@example.com")
    ) == 0

    committed = client.post(
        f"/api/v1/organizations/{organization.id}/imports/{job2}/commit",
        json={"dry_run": False},
        headers=headers,
    )
    assert committed.status_code == 200
    assert committed.json()["committed_rows"] == 1
    assert db_session.scalar(
        select(func.count()).select_from(Contact).where(Contact.email == "ada@example.com")
    ) == 1


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_import_revalidates_and_refuses_new_duplicate(client, db_session) -> None:
    organization, user = _identity(db_session)
    csv_content = "first_name,last_name,email\nNew,Contact,new@example.com\n"
    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    preview = client.post(
        f"/api/v1/organizations/{organization.id}/imports/contacts/preview",
        files={"file": ("contacts.csv", io.BytesIO(csv_content.encode()), "text/csv")},
        headers=headers,
    )
    assert preview.status_code == 201
    job_id = preview.json()["id"]

    concurrent = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Concurrent",
        last_name="User",
        email="new@example.com",
    )
    db_session.add(concurrent)
    db_session.flush()

    commit = client.post(
        f"/api/v1/organizations/{organization.id}/imports/{job_id}/commit",
        json={"dry_run": False},
        headers=headers,
    )
    assert commit.status_code == 409
    assert db_session.scalar(
        select(func.count())
        .select_from(Contact)
        .where(Contact.email == "new@example.com")
    ) == 0


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_member_cannot_import_contacts(client, db_session) -> None:
    organization, user = _identity(db_session, role=MembershipRole.MEMBER)
    token = create_access_token(user.id)
    response = client.post(
        f"/api/v1/organizations/{organization.id}/imports/contacts/preview",
        files={"file": ("contacts.csv", io.BytesIO(b"first_name,last_name\nA,B\n"), "text/csv")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_csv_parser_rejects_missing_required_header() -> None:
    with pytest.raises(ValueError, match="missing required headers"):
        _parse_csv(b"email,phone\nuser@example.com,123\n")


def test_csv_parser_rejects_unsupported_header() -> None:
    with pytest.raises(ValueError, match="unsupported headers"):
        _parse_csv(b"first_name,last_name,address\nAda,Lovelace,London\n")


def test_csv_parser_accepts_utf8_sig() -> None:
    headers, rows = _parse_csv("\ufefffirst_name,last_name\nAda,Lovelace\n".encode("utf-8"))
    assert headers == ["first_name", "last_name"]
    assert rows[0]["first_name"] == "Ada"


def test_csv_parser_rejects_nul_bytes() -> None:
    with pytest.raises(ValueError, match="NUL"):
        _parse_csv(b"first_name,last_name\nAda,\x00Lovelace\n")


def test_csv_parser_rejects_oversized_file() -> None:
    content = b"first_name,last_name\nAda,Lovelace\n" + b"x" * (MAX_FILE_SIZE + 1)
    with pytest.raises(ValueError, match="5 MB"):
        _parse_csv(content)
