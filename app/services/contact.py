from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Company, Contact
from app.services.audit import record_audit


def _snapshot(contact: Contact) -> dict[str, Any]:
    return {
        "id": str(contact.id),
        "organization_id": str(contact.organization_id),
        "company_id": str(contact.company_id) if contact.company_id else None,
        "owner_user_id": str(contact.owner_user_id),
        "first_name": contact.first_name,
        "last_name": contact.last_name,
        "email": contact.email,
        "phone": contact.phone,
        "job_title": contact.job_title,
        "lifecycle": contact.lifecycle,
        "deleted_at": contact.deleted_at.isoformat() if contact.deleted_at else None,
    }


def get_contact(
    db: Session,
    *,
    organization_id: UUID,
    contact_id: UUID,
) -> Contact | None:
    return db.scalar(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .where(Contact.id == contact_id)
        .where(Contact.deleted_at.is_(None))
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
    company = db.scalar(
        select(Company.id)
        .where(Company.organization_id == organization_id)
        .where(Company.id == company_id)
        .where(Company.deleted_at.is_(None))
        .limit(1)
    )
    if company is None:
        raise ValueError("Company not found in this organization")


def create_contact(
    db: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    first_name: str,
    last_name: str,
    email: str | None,
    phone: str | None,
    job_title: str | None,
    lifecycle: str,
    company_id: UUID | None,
) -> Contact:
    _validate_company(db, organization_id=organization_id, company_id=company_id)
    contact = Contact(
        organization_id=organization_id,
        owner_user_id=actor_user_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        phone=phone,
        job_title=job_title,
        lifecycle=lifecycle,
        company_id=company_id,
    )
    db.add(contact)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type="contact",
        entity_id=contact.id,
        action="created",
        summary=f"Created contact {contact.first_name} {contact.last_name}",
        after_data=_snapshot(contact),
    )
    return contact


def update_contact(
    db: Session,
    *,
    contact: Contact,
    actor_user_id: UUID,
    changes: dict[str, object],
) -> Contact:
    if "company_id" in changes:
        company_id = changes["company_id"]
        _validate_company(
            db,
            organization_id=contact.organization_id,
            company_id=company_id if isinstance(company_id, UUID) else None,
        )
    before = _snapshot(contact)
    for key, value in changes.items():
        setattr(contact, key, str(value) if key == "email" and value is not None else value)
    db.flush()
    record_audit(
        db,
        organization_id=contact.organization_id,
        actor_user_id=actor_user_id,
        entity_type="contact",
        entity_id=contact.id,
        action="updated",
        summary=f"Updated contact {contact.first_name} {contact.last_name}",
        before_data=before,
        after_data=_snapshot(contact),
    )
    return contact


def archive_contact(
    db: Session,
    *,
    contact: Contact,
    actor_user_id: UUID,
) -> Contact:
    before = _snapshot(contact)
    contact.deleted_at = datetime.now(UTC)
    db.flush()
    record_audit(
        db,
        organization_id=contact.organization_id,
        actor_user_id=actor_user_id,
        entity_type="contact",
        entity_id=contact.id,
        action="archived",
        summary=f"Archived contact {contact.first_name} {contact.last_name}",
        before_data=before,
        after_data=_snapshot(contact),
    )
    return contact


def search_contacts(
    db: Session,
    *,
    organization_id: UUID,
    query: str | None,
    company_id: UUID | None,
    page: int,
    page_size: int,
) -> tuple[list[Contact], int]:
    statement = (
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .where(Contact.deleted_at.is_(None))
    )
    if query:
        term = f"%{query.strip()}%"
        statement = statement.where(
            or_(
                Contact.first_name.ilike(term),
                Contact.last_name.ilike(term),
                Contact.email.ilike(term),
                Contact.phone.ilike(term),
                Contact.job_title.ilike(term),
            )
        )
    if company_id:
        statement = statement.where(Contact.company_id == company_id)

    total = db.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.scalars(
        statement.order_by(Contact.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return items, total
