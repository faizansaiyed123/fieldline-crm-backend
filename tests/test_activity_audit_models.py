from app.db.base import Base
from app.models import Activity, AuditEvent, Task


def test_activity_task_and_audit_tables_are_registered() -> None:
    assert {
        Activity.__tablename__,
        Task.__tablename__,
        AuditEvent.__tablename__,
    } <= set(Base.metadata.tables)


def test_activity_has_timeline_indexes() -> None:
    names = {index.name for index in Base.metadata.tables[Activity.__tablename__].indexes}
    assert "ix_activities_org_contact_time" in names
    assert "ix_activities_org_company_time" in names
    assert "ix_activities_org_opportunity_time" in names
    assert "ix_activities_org_time" in names


def test_audit_has_entity_and_org_indexes() -> None:
    names = {index.name for index in Base.metadata.tables[AuditEvent.__tablename__].indexes}
    assert "ix_audit_events_org_entity_time" in names
    assert "ix_audit_events_org_time" in names


def test_activity_requires_a_subject() -> None:
    checks = Base.metadata.tables[Activity.__tablename__].constraints
    assert any(check.name == "ck_activity_has_subject" for check in checks)
