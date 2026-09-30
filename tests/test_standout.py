from datetime import UTC, datetime, timedelta
from importlib.util import find_spec

import pytest

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import (
    Activity,
    AutomationRule,
    AutomationRun,
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
from app.services.business_rules import set_rule_value
from app.services.data_quality import build_data_quality_report
from app.services.merge import merge_record
from app.services.pipeline_intelligence import get_stuck_opportunities

POSTGRES_DRIVER_AVAILABLE = find_spec("psycopg") is not None


def _identity(db_session, *, role: MembershipRole = MembershipRole.OWNER):
    organization = Organization(name="Standout Org", slug=f"standout-{id(db_session)}")
    user = User(
        email=f"standout-{id(db_session)}@example.com",
        full_name="Standout User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(organization=organization, user=user, role=role)
    db_session.add_all([organization, user, membership])
    db_session.flush()
    return organization, user


@pytest.mark.skipif(not POSTGRES_DRIVER_AVAILABLE, reason="PostgreSQL driver is required")
def test_data_quality_detects_duplicate_and_missing_channel(client, db_session) -> None:
    organization, user = _identity(db_session)
    first = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Ada",
        last_name="Lovelace",
        email="ada@example.com",
    )
    duplicate = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Ada",
        last_name="Lovelace",
        email="ADA@example.com",
    )
    incomplete = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="No",
        last_name="Channel",
    )
    db_session.add_all([first, duplicate, incomplete])
    db_session.flush()

    report = build_data_quality_report(db_session, organization_id=organization.id)

    assert report.summary.duplicate_contacts == 1
    assert report.summary.incomplete_records >= 1
    assert any(candidate.first_id in {first.id, duplicate.id} for candidate in report.duplicate_candidates)


@pytest.mark.skipif(not POSTGRES_DRIVER_AVAILABLE, reason="PostgreSQL driver is required")
def test_contact_merge_preserves_relationships_and_is_idempotent(db_session) -> None:
    organization, user = _identity(db_session)
    stage = PipelineStage(organization_id=organization.id, name="New", order_index=10)
    db_session.add(stage)
    db_session.flush()

    survivor = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Grace",
        last_name="Hopper",
    )
    merged = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
    )
    db_session.add_all([survivor, merged])
    db_session.flush()

    opportunity = Opportunity(
        organization_id=organization.id,
        owner_user_id=user.id,
        contact_id=merged.id,
        stage_id=stage.id,
        name="Merged Deal",
        status="open",
    )
    task = Task(
        organization_id=organization.id,
        created_by_user_id=user.id,
        contact_id=merged.id,
        title="Merged follow-up",
    )
    activity = Activity(
        organization_id=organization.id,
        actor_user_id=user.id,
        contact_id=merged.id,
        activity_type="note",
        title="Merged note",
    )
    db_session.add_all([opportunity, task, activity])
    db_session.flush()

    operation = merge_record(
        db_session,
        organization_id=organization.id,
        entity_type="contact",
        survivor_id=survivor.id,
        merged_id=merged.id,
        actor_user_id=user.id,
    )
    db_session.commit()

    assert operation.entity_type == "contact"
    assert db_session.get(Contact, merged.id).deleted_at is not None
    assert db_session.get(Contact, survivor.id).email == "grace@example.com"
    assert db_session.get(Opportunity, opportunity.id).contact_id == survivor.id
    assert db_session.get(Task, task.id).contact_id == survivor.id
    assert db_session.get(Activity, activity.id).contact_id == survivor.id

    with pytest.raises(ValueError, match="already been merged"):
        merge_record(
            db_session,
            organization_id=organization.id,
            entity_type="contact",
            survivor_id=survivor.id,
            merged_id=merged.id,
            actor_user_id=user.id,
        )


@pytest.mark.skipif(not POSTGRES_DRIVER_AVAILABLE, reason="PostgreSQL driver is required")
def test_business_rule_changes_attention_threshold(client, db_session) -> None:
    organization, user = _identity(db_session)
    stale = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        first_name="Stale",
        last_name="Lead",
        lifecycle="lead",
        created_at=datetime.now(UTC) - timedelta(days=6),
    )
    db_session.add(stale)
    db_session.flush()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    rule_url = f"/api/v1/organizations/{organization.id}/business-rules/contact_inactivity_days"
    changed = client.patch(rule_url, json={"value": 5}, headers=headers)
    assert changed.status_code == 200
    assert changed.json()["value"] == 5

    attention = client.get(
        f"/api/v1/organizations/{organization.id}/attention",
        headers=headers,
    )
    assert attention.status_code == 200
    assert any(item["entity_id"] == str(stale.id) for item in attention.json()["items"])


@pytest.mark.skipif(not POSTGRES_DRIVER_AVAILABLE, reason="PostgreSQL driver is required")
def test_stuck_opportunity_explains_stage_age_and_missing_next_action(db_session) -> None:
    organization, user = _identity(db_session)
    stage = PipelineStage(organization_id=organization.id, name="Proposal", order_index=20)
    db_session.add(stage)
    db_session.flush()
    opportunity = Opportunity(
        organization_id=organization.id,
        owner_user_id=user.id,
        stage_id=stage.id,
        name="Stuck deal",
        status="open",
        updated_at=datetime.now(UTC) - timedelta(days=30),
    )
    db_session.add(opportunity)
    db_session.flush()

    from app.models import AuditEvent

    db_session.add(
        AuditEvent(
            organization_id=organization.id,
            actor_user_id=user.id,
            entity_type="opportunity",
            entity_id=opportunity.id,
            action="created",
            summary="created",
            after_data={"stage_id": str(stage.id)},
            created_at=datetime.now(UTC) - timedelta(days=30),
        )
    )
    db_session.flush()

    set_rule_value(
        db_session,
        organization_id=organization.id,
        key="opportunity_stage_stuck_days",
        value=14,
        actor_user_id=user.id,
    )
    db_session.flush()

    items = get_stuck_opportunities(db_session, organization_id=organization.id, limit=10)

    assert items
    assert items[0].id == opportunity.id
    assert items[0].stage_age_days >= 29
    assert not items[0].has_next_action
    assert any("stage" in reason.lower() for reason in items[0].reasons)


@pytest.mark.skipif(not POSTGRES_DRIVER_AVAILABLE, reason="PostgreSQL driver is required")
def test_relationship_graph_is_tenant_scoped(client, db_session) -> None:
    organization, user = _identity(db_session)
    company = Company(
        organization_id=organization.id,
        owner_user_id=user.id,
        name="Graph Co",
    )
    db_session.add(company)
    db_session.flush()

    contact = Contact(
        organization_id=organization.id,
        owner_user_id=user.id,
        company_id=company.id,
        first_name="Graph",
        last_name="User",
    )
    db_session.add(contact)
    db_session.flush()

    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/organizations/{organization.id}/contacts/{contact.id}/relationship-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert any(node["type"] == "contact" for node in body["nodes"])
    assert any(node["type"] == "company" for node in body["nodes"])
    assert any(edge["label"] == "works at" for edge in body["edges"])


@pytest.mark.skipif(not POSTGRES_DRIVER_AVAILABLE, reason="PostgreSQL driver is required")
def test_automation_history_is_admin_scoped(client, db_session) -> None:
    organization, user = _identity(db_session)
    rule = AutomationRule(
        organization_id=organization.id,
        name="History rule",
        trigger="opportunity.won",
        action_type="create_task",
        action_config={"title": "Handoff", "priority": "normal", "due_days": 1},
        enabled=True,
    )
    db_session.add(rule)
    db_session.flush()
    run = AutomationRun(
        organization_id=organization.id,
        rule_id=rule.id,
        event_key="opportunity:event:won",
        status="completed",
        result={"task_id": "demo"},
        completed_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.flush()

    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/organizations/{organization.id}/automation/runs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()[0]["workflow"] == "History rule"
    assert response.json()[0]["status"] == "completed"


@pytest.mark.skipif(not POSTGRES_DRIVER_AVAILABLE, reason="PostgreSQL driver is required")
def test_system_health_is_available_to_admin(client, db_session) -> None:
    organization, user = _identity(db_session)
    token = create_access_token(user.id)
    response = client.get(
        f"/api/v1/organizations/{organization.id}/system-health",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] in {"ok", "warning"}
    assert body["checks"]["database"]["status"] == "ok"
    assert "migrations" in body["checks"]
