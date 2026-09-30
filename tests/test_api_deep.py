from datetime import UTC, datetime, timedelta
from importlib.util import find_spec
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import (
    Activity,
    Company,
    Contact,
    Membership,
    MembershipRole,
    Opportunity,
    Organization,
    PipelineStage,
    Task,
    User,
)

pytestmark = pytest.mark.skipif(
    find_spec("psycopg") is None,
    reason="PostgreSQL driver is required for deep API integration tests",
)

EXPECTED_ROUTES = {
    "/api/v1/health": {"GET"},
    "/api/v1/ready": {"GET"},
    "/api/v1/auth/signup": {"POST"},
    "/api/v1/auth/login": {"POST"},
    "/api/v1/auth/refresh": {"POST"},
    "/api/v1/auth/logout": {"POST"},
    "/api/v1/auth/me": {"GET"},
    "/api/v1/organizations/{organization_id}/membership": {"GET"},
    "/api/v1/organizations/{organization_id}/admin-access": {"GET"},
    "/api/v1/organizations/{organization_id}/companies": {"GET", "POST"},
    "/api/v1/organizations/{organization_id}/companies/{company_id}": {"GET", "PATCH", "DELETE"},
    "/api/v1/organizations/{organization_id}/contacts": {"GET", "POST"},
    "/api/v1/organizations/{organization_id}/contacts/{contact_id}": {"GET", "PATCH", "DELETE"},
    "/api/v1/organizations/{organization_id}/pipeline/stages": {"GET", "POST"},
    "/api/v1/organizations/{organization_id}/opportunities": {"GET", "POST"},
    "/api/v1/organizations/{organization_id}/opportunities/{opportunity_id}": {"GET", "PATCH", "DELETE"},
    "/api/v1/organizations/{organization_id}/contacts/{contact_id}/timeline": {"GET"},
    "/api/v1/organizations/{organization_id}/attention": {"GET"},
    "/api/v1/organizations/{organization_id}/automation/rules": {"GET", "POST"},
    "/api/v1/organizations/{organization_id}/automation/rules/{rule_id}": {"PATCH"},
    "/api/v1/organizations/{organization_id}/imports/contacts/preview": {"POST"},
    "/api/v1/organizations/{organization_id}/imports/{job_id}": {"GET"},
    "/api/v1/organizations/{organization_id}/imports/{job_id}/commit": {"POST"},
    "/api/v1/organizations/{organization_id}/saved-views": {"GET", "POST"},
    "/api/v1/organizations/{organization_id}/saved-views/{view_id}": {"GET", "PATCH", "DELETE"},
    "/api/v1/organizations/{organization_id}/saved-views/{view_id}/execute": {"GET"},
    "/api/v1/organizations/{organization_id}/data-quality": {"GET"},
    "/api/v1/organizations/{organization_id}/data-quality/{entity_type}/{merged_id}/merge": {"POST"},
    "/api/v1/organizations/{organization_id}/business-rules": {"GET"},
    "/api/v1/organizations/{organization_id}/business-rules/{key}": {"PATCH"},
    "/api/v1/organizations/{organization_id}/work-planner": {"GET"},
    "/api/v1/organizations/{organization_id}/pipeline/stuck": {"GET"},
    "/api/v1/organizations/{organization_id}/automation/runs": {"GET"},
    "/api/v1/organizations/{organization_id}/automation/runs/{run_id}": {"GET"},
    "/api/v1/organizations/{organization_id}/contacts/{contact_id}/relationship-graph": {"GET"},
    "/api/v1/organizations/{organization_id}/system-health": {"GET"},
    "/api/v1/organizations/{organization_id}/contacts/{contact_id}/relationship-health": {"GET"},
}

def identity(db_session, *, role: MembershipRole = MembershipRole.OWNER, suffix: str | None = None):
    key = suffix or uuid4().hex
    organization = Organization(name=f"Deep Test Org {key}", slug=f"deep-{key}")
    user = User(
        email=f"deep-{key}@example.com",
        full_name="Deep Test User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(organization=organization, user=user, role=role)
    db_session.add_all([organization, user, membership])
    db_session.flush()
    return organization, user


def headers(user):
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def stage(db_session, organization_id, *, name="Qualified", closed=False, won=False):
    value = PipelineStage(
        organization_id=organization_id,
        name=name,
        order_index=30 if not closed else 50,
        win_probability=1 if won else 0.5 if not closed else 0,
        is_closed=closed,
        is_won=won,
    )
    db_session.add(value)
    db_session.flush()
    return value


def test_openapi_route_registration_is_complete(client):
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]

    actual = {
        path: {
            method.upper()
            for method in operations
            if method.lower() in {"get", "post", "patch", "delete"}
        }
        for path, operations in paths.items()
    }
    assert actual == EXPECTED_ROUTES


def test_health_and_auth_end_to_end(client, db_session):
    assert client.get("/api/v1/health").json() == {
        "status": "ok",
        "service": "fieldline-api",
    }

    ready = client.get("/api/v1/ready")
    assert ready.status_code == 200
    assert ready.json()["database"] == "ok"

    signup_payload = {
        "organization_name": f"Auth {uuid4().hex}",
        "full_name": "Auth Deep User",
        "email": f"auth-{uuid4().hex}@example.com",
        "password": "Correct Horse Battery Staple",
    }
    signup = client.post("/api/v1/auth/signup", json=signup_payload)
    assert signup.status_code == 201
    body = signup.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["memberships"][0]["role"] == "owner"

    me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == signup_payload["email"]

    bad_login = client.post(
        "/api/v1/auth/login",
        json={"email": signup_payload["email"], "password": "wrong-password"},
    )
    assert bad_login.status_code == 401

    login = client.post("/api/v1/auth/login", json={"email": signup_payload["email"], "password": signup_payload["password"]})
    assert login.status_code == 200
    csrf = client.cookies.get("fieldline_csrf")
    refresh = client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": csrf})
    assert refresh.status_code == 200
    assert refresh.json()["user"]["id"] == login.json()["user"]["id"]

    old_refresh = client.cookies.get("fieldline_refresh")
    old_csrf = client.cookies.get("fieldline_csrf")
    logout = client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": old_csrf})
    assert logout.status_code == 204
    client.cookies.set("fieldline_refresh", old_refresh)
    client.cookies.set("fieldline_csrf", old_csrf)
    assert client.post("/api/v1/auth/refresh", headers={"X-CSRF-Token": old_csrf}).status_code == 401

    organization = db_session.scalar(select(Organization).where(Organization.slug == signup_payload["organization_name"].lower().replace(" ", "-")))
    assert organization is not None


def test_organization_membership_and_admin_access(client, db_session):
    organization, owner = identity(db_session)
    owner_headers = headers(owner)
    membership = client.get(f"/api/v1/organizations/{organization.id}/membership", headers=owner_headers)
    assert membership.status_code == 200
    assert membership.json()["role"] == "owner"

    admin_access = client.get(f"/api/v1/organizations/{organization.id}/admin-access", headers=owner_headers)
    assert admin_access.status_code == 200

    other, member = identity(db_session, role=MembershipRole.MEMBER, suffix=uuid4().hex)
    blocked = client.get(f"/api/v1/organizations/{other.id}/admin-access", headers=headers(member))
    assert blocked.status_code == 403

    no_auth = client.get(f"/api/v1/organizations/{organization.id}/membership")
    assert no_auth.status_code == 401


def test_company_api_crud_validation_and_tenant_scope(client, db_session):
    organization, owner = identity(db_session)
    other, other_user = identity(db_session, suffix=uuid4().hex)
    base = f"/api/v1/organizations/{organization.id}/companies"
    h = headers(owner)

    assert client.get(base).status_code == 401
    created = client.post(base, json={"name": "Acme", "website": "https://acme.example", "phone": "123"}, headers=h)
    assert created.status_code == 201
    cid = created.json()["id"]

    assert client.post(base, json={"name": "acme"} , headers=h).status_code == 409
    assert client.get(f"{base}/{cid}", headers=h).status_code == 200
    updated = client.patch(f"{base}/{cid}", json={"phone": "+91 999"}, headers=h)
    assert updated.status_code == 200 and updated.json()["phone"] == "+91 999"
    assert client.patch(f"{base}/{cid}", json={"name": "   "}, headers=h).status_code == 422
    assert client.get(f"/api/v1/organizations/{other.id}/companies", headers=h).status_code == 403
    assert client.delete(f"{base}/{cid}", headers=h).status_code == 204
    assert client.get(f"{base}/{cid}", headers=h).status_code == 404


def test_contact_api_crud_search_validation_and_tenant_scope(client, db_session):
    organization, owner = identity(db_session)
    other, other_user = identity(db_session, suffix=uuid4().hex)
    company = Company(organization_id=organization.id, owner_user_id=owner.id, name="Contact Co")
    db_session.add(company)
    db_session.flush()
    base = f"/api/v1/organizations/{organization.id}/contacts"
    h = headers(owner)

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
        headers=h,
    )
    assert created.status_code == 201
    cid = created.json()["id"]
    assert created.json()["email"] == "ada@example.com"
    assert client.get(f"{base}?q=lovelace&page=1&page_size=10", headers=h).json()["total"] == 1
    assert client.get(f"{base}/{cid}", headers=h).status_code == 200
    assert client.patch(f"{base}/{cid}", json={"lifecycle": "customer"}, headers=h).status_code == 200
    assert client.patch(f"{base}/{cid}", json={"first_name": ""}, headers=h).status_code == 422
    assert client.delete(f"{base}/{cid}", headers=h).status_code == 204
    assert client.get(base, headers=h).json()["total"] == 0

    foreign_company = Company(organization_id=other.id, owner_user_id=other_user.id, name="Foreign")
    db_session.add(foreign_company)
    db_session.flush()
    response = client.post(
        base,
        json={"first_name": "Grace", "last_name": "Hopper", "company_id": str(foreign_company.id)},
        headers=h,
    )
    assert response.status_code == 400


def test_pipeline_and_opportunity_api_full_flow(client, db_session):
    organization, owner = identity(db_session)
    h = headers(owner)
    pipeline_base = f"/api/v1/organizations/{organization.id}/pipeline/stages"
    stages = client.get(pipeline_base, headers=h)
    assert stages.status_code == 200
    custom = client.post(pipeline_base, json={"name": "Negotiation", "win_probability": 0.7}, headers=h)
    assert custom.status_code == 201

    proposal = stage(db_session, organization.id, name=f"Proposal-{uuid4().hex[:6]}")
    won = stage(db_session, organization.id, name=f"Won-{uuid4().hex[:6]}", closed=True, won=True)
    company = Company(organization_id=organization.id, owner_user_id=owner.id, name="Opportunity Co")
    db_session.add(company)
    db_session.flush()

    base = f"/api/v1/organizations/{organization.id}/opportunities"
    created = client.post(
        base,
        json={"name": "Big Deal", "stage_id": str(proposal.id), "amount": "12500.00", "company_id": str(company.id)},
        headers=h,
    )
    assert created.status_code == 201
    oid = created.json()["id"]
    assert client.get(base, headers=h).status_code == 200
    assert client.get(f"{base}/{oid}", headers=h).status_code == 200
    assert client.patch(f"{base}/{oid}", json={"name": "Big Deal Updated"}, headers=h).status_code == 200
    assert client.patch(f"{base}/{oid}", json={"stage_id": str(won.id)}, headers=h).status_code == 200
    assert client.get(f"{base}?status=won&page=1&page_size=10", headers=h).json()["total"] == 1
    assert client.delete(f"{base}/{oid}", headers=h).status_code == 204
    assert client.get(f"{base}/{oid}", headers=h).status_code == 404


def test_timeline_attention_relationship_health_and_graph(client, db_session):
    organization, owner = identity(db_session)
    h = headers(owner)
    current = stage(db_session, organization.id, name="Current")
    company = Company(organization_id=organization.id, owner_user_id=owner.id, name="Context Co")
    db_session.add(company)
    db_session.flush()
    contact = Contact(
        organization_id=organization.id,
        owner_user_id=owner.id,
        company_id=company.id,
        first_name="Ada",
        last_name="Context",
        email="ada-context@example.com",
        lifecycle="customer",
    )
    stale = Contact(
        organization_id=organization.id,
        owner_user_id=owner.id,
        first_name="Stale",
        last_name="Lead",
        lifecycle="lead",
        created_at=datetime.now(UTC) - timedelta(days=30),
    )
    db_session.add_all([contact, stale])
    db_session.flush()

    overdue = Task(
        organization_id=organization.id,
        created_by_user_id=owner.id,
        contact_id=contact.id,
        title="Follow up",
        due_at=datetime.now(UTC) - timedelta(days=2),
    )
    old_opportunity = Opportunity(
        organization_id=organization.id,
        owner_user_id=owner.id,
        contact_id=contact.id,
        company_id=company.id,
        stage_id=current.id,
        name="Renewal",
        status="open",
        expected_close_date=(datetime.now(UTC) - timedelta(days=2)).date(),
    )
    db_session.add_all([overdue, old_opportunity])
    db_session.flush()
    db_session.add(
        Activity(
            organization_id=organization.id,
            actor_user_id=owner.id,
            contact_id=contact.id,
            activity_type="call",
            title="Renewal call",
            occurred_at=datetime.now(UTC) - timedelta(days=2),
            activity_metadata={},
        )
    )
    db_session.flush()

    timeline_url = f"/api/v1/organizations/{organization.id}/contacts/{contact.id}/timeline"
    timeline = client.get(f"{timeline_url}?limit=10", headers=h)
    assert timeline.status_code == 200
    assert {"activity", "task"} <= {item["kind"] for item in timeline.json()["items"]}

    attention = client.get(f"/api/v1/organizations/{organization.id}/attention?limit=10", headers=h)
    assert attention.status_code == 200
    assert any(item["entity_id"] == str(overdue.id) for item in attention.json()["items"])
    assert any(item["entity_id"] == str(old_opportunity.id) for item in attention.json()["items"])
    assert any(item["entity_id"] == str(stale.id) for item in attention.json()["items"])

    health = client.get(
        f"/api/v1/organizations/{organization.id}/contacts/{contact.id}/relationship-health",
        headers=h,
    )
    assert health.status_code == 200
    assert health.json()["contact_id"] == str(contact.id)

    graph = client.get(
        f"/api/v1/organizations/{organization.id}/contacts/{contact.id}/relationship-graph",
        headers=h,
    )
    assert graph.status_code == 200
    assert any(node["type"] == "contact" for node in graph.json()["nodes"])
    assert any(edge["label"] == "works at" for edge in graph.json()["edges"])

    assert client.get(
        f"/api/v1/organizations/{uuid4()}/contacts/{contact.id}/relationship-health",
        headers=h,
    ).status_code == 403


def test_automation_rule_and_history_endpoints(client, db_session):
    organization, owner = identity(db_session)
    h = headers(owner)
    rule_base = f"/api/v1/organizations/{organization.id}/automation/rules"
    listed = client.get(rule_base, headers=h)
    assert listed.status_code == 200

    created = client.post(
        rule_base,
        json={
            "name": "Handoff",
            "trigger": "opportunity.won",
            "action_type": "create_task",
            "action_config": {"title": "Start handoff", "priority": "high", "due_days": 1},
        },
        headers=h,
    )
    assert created.status_code == 201
    rid = created.json()["id"]
    assert client.patch(f"{rule_base}/{rid}", json={"enabled": False}, headers=h).status_code == 200
    assert client.patch(f"{rule_base}/{rid}", json={"enabled": True}, headers=h).status_code == 200

    open_stage = stage(db_session, organization.id, name="Open")
    won_stage = stage(db_session, organization.id, name="Won", closed=True, won=True)
    opportunity = Opportunity(
        organization_id=organization.id,
        owner_user_id=owner.id,
        stage_id=open_stage.id,
        name="Automated Deal",
        status="open",
    )
    db_session.add(opportunity)
    db_session.flush()

    changed = client.patch(
        f"/api/v1/organizations/{organization.id}/opportunities/{opportunity.id}",
        json={"stage_id": str(won_stage.id)},
        headers=h,
    )
    assert changed.status_code == 200

    runs = client.get(f"/api/v1/organizations/{organization.id}/automation/runs", headers=h)
    assert runs.status_code == 200
    assert runs.json()
    run_id = runs.json()[0]["id"]
    detail = client.get(f"/api/v1/organizations/{organization.id}/automation/runs/{run_id}", headers=h)
    assert detail.status_code == 200

    other, member = identity(db_session, role=MembershipRole.MEMBER, suffix=uuid4().hex)
    assert client.post(
        f"/api/v1/organizations/{other.id}/automation/rules",
        json={
            "name": "Blocked",
            "trigger": "opportunity.won",
            "action_type": "create_task",
            "action_config": {"title": "Blocked", "priority": "normal", "due_days": 1},
        },
        headers=headers(member),
    ).status_code == 403


def test_import_api_preview_get_dry_run_and_commit(client, db_session):
    organization, owner = identity(db_session)
    h = headers(owner)
    base = f"/api/v1/organizations/{organization.id}/imports"
    csv_data = b"first_name,last_name,email,phone,lifecycle\nAda,Lovelace,ada-import@example.com,123,prospect\nGrace,Hopper,grace-import@example.com,456,lead\n"

    preview = client.post(
        f"{base}/contacts/preview",
        files={"file": ("contacts.csv", csv_data, "text/csv")},
        headers=h,
    )
    assert preview.status_code == 201
    body = preview.json()
    assert body["valid_rows"] == 2
    job_id = body["id"]

    fetched = client.get(f"{base}/{job_id}", headers=h)
    assert fetched.status_code == 200

    dry = client.post(f"{base}/{job_id}/commit", json={"dry_run": True}, headers=h)
    assert dry.status_code == 200
    assert dry.json()["would_create"] == 2

    commit = client.post(f"{base}/{job_id}/commit", json={"dry_run": False}, headers=h)
    assert commit.status_code == 200
    assert commit.json()["committed_rows"] == 2

    assert client.get(f"{base}/00000000-0000-0000-0000-000000000000", headers=h).status_code == 404

    member_org, member = identity(db_session, role=MembershipRole.MEMBER, suffix=uuid4().hex)
    blocked = client.post(
        f"/api/v1/organizations/{member_org.id}/imports/contacts/preview",
        files={"file": ("contacts.csv", csv_data, "text/csv")},
        headers=headers(member),
    )
    assert blocked.status_code == 403


def test_saved_views_full_lifecycle(client, db_session):
    organization, owner = identity(db_session)
    h = headers(owner)
    contact = Contact(
        organization_id=organization.id,
        owner_user_id=owner.id,
        first_name="Ada",
        last_name="Saved",
        email="ada-saved@example.com",
        lifecycle="prospect",
    )
    db_session.add(contact)
    db_session.flush()

    base = f"/api/v1/organizations/{organization.id}/saved-views"
    created = client.post(
        base,
        json={
            "name": "Prospects",
            "shared": True,
            "definition": {"lifecycle": ["prospect"], "has_email": True, "sort": "name_asc"},
        },
        headers=h,
    )
    assert created.status_code == 201
    vid = created.json()["id"]

    assert client.get(base, headers=h).status_code == 200
    assert client.get(f"{base}/{vid}", headers=h).status_code == 200
    updated = client.patch(
        f"{base}/{vid}",
        json={"name": "Prospects with email", "definition": {"lifecycle": ["prospect"], "has_email": True, "sort": "name_asc"}},
        headers=h,
    )
    assert updated.status_code == 200
    assert updated.json()["definition_version"] == 2

    executed = client.get(f"{base}/{vid}/execute?page=1&page_size=25", headers=h)
    assert executed.status_code == 200
    assert executed.json()["total"] == 1

    assert client.delete(f"{base}/{vid}", headers=h).status_code == 204
    assert client.get(f"{base}/{vid}", headers=h).status_code == 404


def test_standout_endpoints_all_exercised(client, db_session):
    organization, owner = identity(db_session)
    h = headers(owner)
    current = stage(db_session, organization.id, name="Stage")
    company = Company(organization_id=organization.id, owner_user_id=owner.id, name="Quality Co")
    db_session.add(company)
    db_session.flush()

    survivor = Contact(
        organization_id=organization.id,
        owner_user_id=owner.id,
        company_id=company.id,
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
        lifecycle="customer",
    )
    duplicate = Contact(
        organization_id=organization.id,
        owner_user_id=owner.id,
        first_name="Grace",
        last_name="Hopper",
        email="GRACE@example.com",
        lifecycle="customer",
    )
    db_session.add_all([survivor, duplicate])
    db_session.flush()

    quality = client.get(f"/api/v1/organizations/{organization.id}/data-quality", headers=h)
    assert quality.status_code == 200
    assert quality.json()["summary"]["duplicate_contacts"] >= 1

    merged = client.post(
        f"/api/v1/organizations/{organization.id}/data-quality/contact/{duplicate.id}/merge",
        json={"survivor_id": str(survivor.id)},
        headers=h,
    )
    assert merged.status_code == 200
    assert merged.json()["survivor_id"] == str(survivor.id)

    rules = client.get(f"/api/v1/organizations/{organization.id}/business-rules", headers=h)
    assert rules.status_code == 200
    assert rules.json()

    changed = client.patch(
        f"/api/v1/organizations/{organization.id}/business-rules/contact_inactivity_days",
        json={"value": 7},
        headers=h,
    )
    assert changed.status_code == 200
    assert changed.json()["value"] == 7

    planner = client.get(f"/api/v1/organizations/{organization.id}/work-planner?limit=10", headers=h)
    assert planner.status_code == 200
    assert "items" in planner.json()

    stuck = Opportunity(
        organization_id=organization.id,
        owner_user_id=owner.id,
        stage_id=current.id,
        name="Stuck",
        status="open",
        updated_at=datetime.now(UTC) - timedelta(days=30),
    )
    db_session.add(stuck)
    db_session.flush()

    stuck_response = client.get(f"/api/v1/organizations/{organization.id}/pipeline/stuck?limit=10", headers=h)
    assert stuck_response.status_code == 200
    assert "configured_threshold_days" in stuck_response.json()

    system = client.get(f"/api/v1/organizations/{organization.id}/system-health", headers=h)
    assert system.status_code == 200
    assert "checks" in system.json()

    other, member = identity(db_session, role=MembershipRole.MEMBER, suffix=uuid4().hex)
    assert client.get(f"/api/v1/organizations/{other.id}/system-health", headers=headers(member)).status_code == 403

    missing_run = client.get(
        f"/api/v1/organizations/{organization.id}/automation/runs/00000000-0000-0000-0000-000000000000",
        headers=h,
    )
    assert missing_run.status_code == 404


def test_api_bounds_and_privileged_route_guards(client, db_session):
    organization, owner = identity(db_session)
    member_org, member = identity(db_session, role=MembershipRole.MEMBER, suffix=uuid4().hex)
    owner_headers = headers(owner)
    member_headers = headers(member)

    org = f"/api/v1/organizations/{organization.id}"
    assert client.get(f"{org}/contacts?page_size=0", headers=owner_headers).status_code == 422
    assert client.get(f"{org}/attention?limit=101", headers=owner_headers).status_code == 422
    assert client.get(f"{org}/work-planner?limit=51", headers=owner_headers).status_code == 422
    assert client.get(f"{org}/pipeline/stuck?limit=51", headers=owner_headers).status_code == 422
    assert client.get(f"{org}/automation/runs?limit=101", headers=owner_headers).status_code == 422

    assert client.get(
        f"/api/v1/organizations/{member_org.id}/business-rules",
        headers=member_headers,
    ).status_code == 403
    assert client.patch(
        f"/api/v1/organizations/{member_org.id}/business-rules/contact_inactivity_days",
        json={"value": 7},
        headers=member_headers,
    ).status_code == 403

    assert client.post(
        f"/api/v1/organizations/{member_org.id}/automation/rules",
        json={
            "name": "Blocked",
            "trigger": "opportunity.won",
            "action_type": "create_task",
            "action_config": {"title": "Blocked", "priority": "normal", "due_days": 1},
        },
        headers=member_headers,
    ).status_code == 403

    assert client.post(
        f"/api/v1/organizations/{member_org.id}/imports/contacts/preview",
        files={"file": ("contacts.csv", b"first_name,last_name\nA,B\n", "text/csv")},
        headers=member_headers,
    ).status_code == 403

    bad_csv = client.post(
        f"{org}/imports/contacts/preview",
        files={"file": ("bad.csv", b"wrong,header\nA,B\n", "text/csv")},
        headers=owner_headers,
    )
    assert bad_csv.status_code == 400
