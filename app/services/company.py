from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company
from app.services.audit import record_audit


def _snapshot(company: Company) -> dict[str, Any]:
    return {
        "id": str(company.id),
        "organization_id": str(company.organization_id),
        "owner_user_id": str(company.owner_user_id),
        "name": company.name,
        "website": company.website,
        "phone": company.phone,
        "deleted_at": company.deleted_at.isoformat() if company.deleted_at else None,
    }


def get_company(
    db: Session,
    *,
    organization_id: UUID,
    company_id: UUID,
) -> Company | None:
    return db.scalar(
        select(Company)
        .where(Company.organization_id == organization_id)
        .where(Company.id == company_id)
        .where(Company.deleted_at.is_(None))
        .limit(1)
    )


def create_company(
    db: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    name: str,
    website: str | None,
    phone: str | None,
) -> Company:
    duplicate = db.scalar(
        select(Company.id)
        .where(Company.organization_id == organization_id)
        .where(func.lower(Company.name) == name.lower())
        .where(Company.deleted_at.is_(None))
        .limit(1)
    )
    if duplicate:
        raise ValueError("A company with this name already exists")

    company = Company(
        organization_id=organization_id,
        owner_user_id=actor_user_id,
        name=name,
        website=website,
        phone=phone,
    )
    db.add(company)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type="company",
        entity_id=company.id,
        action="created",
        summary=f"Created company {company.name}",
        after_data=_snapshot(company),
    )
    return company


def update_company(
    db: Session,
    *,
    company: Company,
    actor_user_id: UUID,
    changes: dict[str, object],
) -> Company:
    if "name" in changes:
        new_name = str(changes["name"])
        duplicate = db.scalar(
            select(Company.id)
            .where(Company.organization_id == company.organization_id)
            .where(Company.id != company.id)
            .where(func.lower(Company.name) == new_name.lower())
            .where(Company.deleted_at.is_(None))
            .limit(1)
        )
        if duplicate:
            raise ValueError("A company with this name already exists")

    before = _snapshot(company)
    for key, value in changes.items():
        if key == "website" and value is not None:
            value = str(value)
        setattr(company, key, value)
    db.flush()
    record_audit(
        db,
        organization_id=company.organization_id,
        actor_user_id=actor_user_id,
        entity_type="company",
        entity_id=company.id,
        action="updated",
        summary=f"Updated company {company.name}",
        before_data=before,
        after_data=_snapshot(company),
    )
    return company


def archive_company(
    db: Session,
    *,
    company: Company,
    actor_user_id: UUID,
) -> Company:
    before = _snapshot(company)
    company.deleted_at = datetime.now(UTC)
    db.flush()
    record_audit(
        db,
        organization_id=company.organization_id,
        actor_user_id=actor_user_id,
        entity_type="company",
        entity_id=company.id,
        action="archived",
        summary=f"Archived company {company.name}",
        before_data=before,
        after_data=_snapshot(company),
    )
    return company
