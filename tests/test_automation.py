from importlib.util import find_spec

import pytest
from sqlalchemy import func, select

from app.auth.crypto import hash_password
from app.auth.tokens import create_access_token
from app.models import (
    AutomationRule,
    AutomationRun,
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
def test_admin_can_create_rule_and_won_transition_runs_once(client, db_session) -> None:
    organization = Organization(name="Automation Org", slug=f"automation-{id(db_session)}")
    user = User(
        email=f"automation-{id(db_session)}@example.com",
        full_name="Automation User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(
        organization=organization,
        user=user,
        role=MembershipRole.OWNER,
    )
    db_session.add_all([organization, user, membership])
    db_session.flush()

    open_stage = PipelineStage(
        organization_id=organization.id,
        name="Proposal",
        order_index=30,
        win_probability=0.5,
    )
    won_stage = PipelineStage(
        organization_id=organization.id,
        name="Closed Won",
        order_index=50,
        win_probability=1,
        is_closed=True,
        is_won=True,
    )
    db_session.add_all([organization, user, membership, open_stage, won_stage])
    db_session.flush()

    opportunity = Opportunity(
        organization_id=organization.id,
        owner_user_id=user.id,
        stage_id=open_stage.id,
        name="Expansion Deal",
        status="open",
    )
    db_session.add(opportunity)
    db_session.flush()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}
    rules_url = f"/api/v1/organizations/{organization.id}/automation/rules"

    created_rule = client.post(
        rules_url,
        json={
            "name": "Customer handoff",
            "trigger": "opportunity.won",
            "action_type": "create_task",
            "action_config": {
                "title": "Start customer handoff",
                "priority": "high",
                "due_days": 1,
            },
            "enabled": True,
        },
        headers=headers,
    )
    assert created_rule.status_code == 201
    rule_id = created_rule.json()["id"]

    updated = client.patch(
        f"/api/v1/organizations/{organization.id}/opportunities/{opportunity.id}",
        json={"stage_id": str(won_stage.id)},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["status"] == "won"

    task_count = db_session.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.opportunity_id == opportunity.id)
    )
    run_count = db_session.scalar(
        select(func.count())
        .select_from(AutomationRun)
        .where(AutomationRun.rule_id == rule_id)
    )
    assert task_count == 1
    assert run_count == 1

    same_state = client.patch(
        f"/api/v1/organizations/{organization.id}/opportunities/{opportunity.id}",
        json={"name": "Expansion Deal Updated"},
        headers=headers,
    )
    assert same_state.status_code == 200

    assert db_session.scalar(
        select(func.count())
        .select_from(Task)
        .where(Task.opportunity_id == opportunity.id)
    ) == 1
    assert db_session.scalar(
        select(func.count())
        .select_from(AutomationRun)
        .where(AutomationRun.rule_id == rule_id)
    ) == 1

    task = db_session.scalar(
        select(Task).where(Task.opportunity_id == opportunity.id)
    )
    assert task is not None
    assert task.title == "Start customer handoff"
    assert task.priority == "high"
    persisted_rule_id = db_session.scalar(
        select(AutomationRule.id).where(AutomationRule.id == rule_id)
    )
    assert str(persisted_rule_id) == rule_id


@pytest.mark.skipif(
    not POSTGRES_DRIVER_AVAILABLE,
    reason="PostgreSQL driver is required for integration tests",
)
def test_member_cannot_create_automation_rule(client, db_session) -> None:
    organization = Organization(name="Member Org", slug=f"member-automation-{id(db_session)}")
    user = User(
        email=f"member-automation-{id(db_session)}@example.com",
        full_name="Member User",
        password_hash=hash_password("Correct Horse Battery Staple"),
    )
    membership = Membership(
        organization=organization,
        user=user,
        role=MembershipRole.MEMBER,
    )
    db_session.add_all([organization, user, membership])
    db_session.flush()

    token = create_access_token(user.id)
    response = client.post(
        f"/api/v1/organizations/{organization.id}/automation/rules",
        json={
            "name": "Blocked rule",
            "trigger": "opportunity.won",
            "action_type": "create_task",
            "action_config": {"title": "Blocked", "priority": "normal", "due_days": 1},
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403
