from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company, Contact, Opportunity, PipelineStage
from app.services.audit import record_audit
from app.services.automation import run_opportunity_automations
from app.services.pipeline import get_stage


def _snapshot(opportunity: Opportunity) -> dict[str, Any]:
    return {
        "id": str(opportunity.id),
        "organization_id": str(opportunity.organization_id),
        "owner_user_id": str(opportunity.owner_user_id),
        "company_id": str(opportunity.company_id) if opportunity.company_id else None,
        "contact_id": str(opportunity.contact_id) if opportunity.contact_id else None,
        "stage_id": str(opportunity.stage_id),
        "name": opportunity.name,
        "amount": str(opportunity.amount) if opportunity.amount is not None else None,
        "status": opportunity.status,
        "expected_close_date": (
            opportunity.expected_close_date.isoformat()
            if opportunity.expected_close_date
            else None
        ),
        "lost_reason": opportunity.lost_reason,
        "deleted_at": opportunity.deleted_at.isoformat() if opportunity.deleted_at else None,
    }


def get_opportunity(
    db: Session,
    *,
    organization_id: UUID,
    opportunity_id: UUID,
) -> Opportunity | None:
    return db.scalar(
        select(Opportunity)
        .where(Opportunity.organization_id == organization_id)
        .where(Opportunity.id == opportunity_id)
        .where(Opportunity.deleted_at.is_(None))
        .limit(1)
    )


def _validate_company(
    db: Session,
    *,
    organization_id: UUID,
    company_id: UUID | None,
) -> None:
    if company_id is None:
        return
    exists = db.scalar(
        select(Company.id)
        .where(Company.organization_id == organization_id)
        .where(Company.id == company_id)
        .where(Company.deleted_at.is_(None))
        .limit(1)
    )
    if exists is None:
        raise ValueError("Company not found in this organization")


def _validate_contact(
    db: Session,
    *,
    organization_id: UUID,
    contact_id: UUID | None,
) -> Contact | None:
    if contact_id is None:
        return None
    contact = db.scalar(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .where(Contact.id == contact_id)
        .where(Contact.deleted_at.is_(None))
        .limit(1)
    )
    if contact is None:
        raise ValueError("Contact not found in this organization")
    return contact


def _resolve_status(stage: PipelineStage, requested_status: str | None) -> str:
    if stage.is_won:
        return "won"
    if stage.is_closed:
        return "lost"
    if requested_status in {"won", "lost"}:
        raise ValueError("Closed opportunities must use a closed pipeline stage")
    return "open"


def create_opportunity(
    db: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    name: str,
    stage_id: UUID,
    amount,
    company_id: UUID | None,
    contact_id: UUID | None,
    expected_close_date,
) -> Opportunity:
    stage = get_stage(db, organization_id=organization_id, stage_id=stage_id)
    if stage is None:
        raise ValueError("Pipeline stage not found in this organization")
    if stage.is_closed:
        raise ValueError("New opportunities must start on an open pipeline stage")

    _validate_company(db, organization_id=organization_id, company_id=company_id)
    contact = _validate_contact(
        db,
        organization_id=organization_id,
        contact_id=contact_id,
    )
    if contact and contact.company_id and company_id != contact.company_id:
        raise ValueError("Contact belongs to a different company")

    opportunity = Opportunity(
        organization_id=organization_id,
        owner_user_id=actor_user_id,
        company_id=company_id,
        contact_id=contact_id,
        stage_id=stage_id,
        name=name,
        amount=amount,
        status="open",
        expected_close_date=expected_close_date,
    )
    db.add(opportunity)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type="opportunity",
        entity_id=opportunity.id,
        action="created",
        summary=f"Created opportunity {opportunity.name}",
        after_data=_snapshot(opportunity),
    )
    return opportunity


def update_opportunity(
    db: Session,
    *,
    opportunity: Opportunity,
    actor_user_id: UUID,
    changes: dict[str, object],
) -> Opportunity:
    company_id = changes.get("company_id", opportunity.company_id)
    contact_id = changes.get("contact_id", opportunity.contact_id)
    stage_id = changes.get("stage_id", opportunity.stage_id)

    if company_id is not None and not isinstance(company_id, UUID):
        raise ValueError("Invalid company")
    if contact_id is not None and not isinstance(contact_id, UUID):
        raise ValueError("Invalid contact")
    if stage_id is not None and not isinstance(stage_id, UUID):
        raise ValueError("Invalid pipeline stage")

    _validate_company(db, organization_id=opportunity.organization_id, company_id=company_id)
    contact = _validate_contact(
        db,
        organization_id=opportunity.organization_id,
        contact_id=contact_id,
    )
    stage = get_stage(db, organization_id=opportunity.organization_id, stage_id=stage_id)
    if stage is None:
        raise ValueError("Pipeline stage not found in this organization")
    if contact and contact.company_id and company_id != contact.company_id:
        raise ValueError("Contact belongs to a different company")

    before = _snapshot(opportunity)
    previous_status = opportunity.status
    for key, value in changes.items():
        setattr(opportunity, key, value)

    if "stage_id" in changes or "status" in changes:
        requested_status = changes.get("status")
        opportunity.status = _resolve_status(
            stage,
            str(requested_status) if requested_status is not None else None,
        )

    if opportunity.status == "lost" and not opportunity.lost_reason:
        raise ValueError("Lost opportunities require a lost reason")
    if opportunity.status != "lost":
        opportunity.lost_reason = None

    db.flush()
    run_opportunity_automations(
        db,
        opportunity=opportunity,
        previous_status=previous_status,
        actor_user_id=actor_user_id,
    )
    record_audit(
        db,
        organization_id=opportunity.organization_id,
        actor_user_id=actor_user_id,
        entity_type="opportunity",
        entity_id=opportunity.id,
        action="updated",
        summary=f"Updated opportunity {opportunity.name}",
        before_data=before,
        after_data=_snapshot(opportunity),
    )
    return opportunity


def archive_opportunity(
    db: Session,
    *,
    opportunity: Opportunity,
    actor_user_id: UUID,
) -> Opportunity:
    before = _snapshot(opportunity)
    opportunity.deleted_at = datetime.now(UTC)
    db.flush()
    record_audit(
        db,
        organization_id=opportunity.organization_id,
        actor_user_id=actor_user_id,
        entity_type="opportunity",
        entity_id=opportunity.id,
        action="archived",
        summary=f"Archived opportunity {opportunity.name}",
        before_data=before,
        after_data=_snapshot(opportunity),
    )
    return opportunity


def search_opportunities(
    db: Session,
    *,
    organization_id: UUID,
    query: str | None,
    stage_id: UUID | None,
    status: str | None,
    page: int,
    page_size: int,
) -> tuple[list[Opportunity], int]:
    statement = (
        select(Opportunity)
        .where(Opportunity.organization_id == organization_id)
        .where(Opportunity.deleted_at.is_(None))
    )
    if query:
        term = f"%{query.strip()}%"
        statement = statement.where(Opportunity.name.ilike(term))
    if stage_id:
        statement = statement.where(Opportunity.stage_id == stage_id)
    if status:
        statement = statement.where(Opportunity.status == status)

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(
        statement.order_by(Opportunity.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return items, total
