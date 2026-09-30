from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Activity, Company, Contact, MergeOperation, Opportunity, Task
from app.services.audit import record_audit


def _merge_contact(
    db: Session,
    *,
    organization_id: UUID,
    survivor_id: UUID,
    merged_id: UUID,
    actor_user_id: UUID,
) -> MergeOperation:
    survivor = db.scalar(
        select(Contact)
        .where(Contact.organization_id == organization_id, Contact.id == survivor_id)
        .where(Contact.deleted_at.is_(None))
        .with_for_update()
    )
    merged = db.scalar(
        select(Contact)
        .where(Contact.organization_id == organization_id, Contact.id == merged_id)
        .where(Contact.deleted_at.is_(None))
        .with_for_update()
    )
    if survivor is None or merged is None:
        raise ValueError("Both contacts must exist and be active")
    if survivor_id == merged_id:
        raise ValueError("A record cannot be merged into itself")

    if survivor.email is None and merged.email is not None:
        survivor.email = merged.email
    if survivor.phone is None and merged.phone is not None:
        survivor.phone = merged.phone
    if survivor.job_title is None and merged.job_title is not None:
        survivor.job_title = merged.job_title
    if survivor.company_id is None and merged.company_id is not None:
        survivor.company_id = merged.company_id

    counts = {
        "activities": db.execute(
            update(Activity)
            .where(Activity.organization_id == organization_id, Activity.contact_id == merged_id)
            .values(contact_id=survivor_id)
        ).rowcount or 0,
        "tasks": db.execute(
            update(Task)
            .where(Task.organization_id == organization_id, Task.contact_id == merged_id)
            .values(contact_id=survivor_id)
        ).rowcount or 0,
        "opportunities": db.execute(
            update(Opportunity)
            .where(Opportunity.organization_id == organization_id, Opportunity.contact_id == merged_id)
            .values(contact_id=survivor_id)
        ).rowcount or 0,
    }

    merged.deleted_at = datetime.now(UTC)
    db.flush()

    operation = MergeOperation(
        organization_id=organization_id,
        entity_type="contact",
        survivor_id=survivor_id,
        merged_id=merged_id,
        actor_user_id=actor_user_id,
        status="completed",
        completed_at=datetime.now(UTC),
    )
    db.add(operation)
    db.flush()

    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type="contact",
        entity_id=survivor_id,
        action="merged",
        summary=f"Merged contact {merged.first_name} {merged.last_name} into {survivor.first_name} {survivor.last_name}",
        after_data={"merged_contact_id": str(merged_id), "transferred": counts},
    )
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type="contact",
        entity_id=merged_id,
        action="merged_away",
        summary=f"Contact merged into {survivor.first_name} {survivor.last_name}",
        after_data={"survivor_contact_id": str(survivor_id)},
    )
    return operation


def _merge_company(
    db: Session,
    *,
    organization_id: UUID,
    survivor_id: UUID,
    merged_id: UUID,
    actor_user_id: UUID,
) -> MergeOperation:
    survivor = db.scalar(
        select(Company)
        .where(Company.organization_id == organization_id, Company.id == survivor_id)
        .where(Company.deleted_at.is_(None))
        .with_for_update()
    )
    merged = db.scalar(
        select(Company)
        .where(Company.organization_id == organization_id, Company.id == merged_id)
        .where(Company.deleted_at.is_(None))
        .with_for_update()
    )
    if survivor is None or merged is None:
        raise ValueError("Both companies must exist and be active")
    if survivor_id == merged_id:
        raise ValueError("A record cannot be merged into itself")

    if survivor.website is None and merged.website is not None:
        survivor.website = merged.website
    if survivor.phone is None and merged.phone is not None:
        survivor.phone = merged.phone

    counts = {
        "contacts": db.execute(
            update(Contact)
            .where(Contact.organization_id == organization_id, Contact.company_id == merged_id)
            .values(company_id=survivor_id)
        ).rowcount or 0,
        "opportunities": db.execute(
            update(Opportunity)
            .where(Opportunity.organization_id == organization_id, Opportunity.company_id == merged_id)
            .values(company_id=survivor_id)
        ).rowcount or 0,
        "activities": db.execute(
            update(Activity)
            .where(Activity.organization_id == organization_id, Activity.company_id == merged_id)
            .values(company_id=survivor_id)
        ).rowcount or 0,
        "tasks": db.execute(
            update(Task)
            .where(Task.organization_id == organization_id, Task.company_id == merged_id)
            .values(company_id=survivor_id)
        ).rowcount or 0,
    }

    merged.deleted_at = datetime.now(UTC)
    db.flush()

    operation = MergeOperation(
        organization_id=organization_id,
        entity_type="company",
        survivor_id=survivor_id,
        merged_id=merged_id,
        actor_user_id=actor_user_id,
        status="completed",
        completed_at=datetime.now(UTC),
    )
    db.add(operation)
    db.flush()

    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type="company",
        entity_id=survivor_id,
        action="merged",
        summary=f"Merged company {merged.name} into {survivor.name}",
        after_data={"merged_company_id": str(merged_id), "transferred": counts},
    )
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type="company",
        entity_id=merged_id,
        action="merged_away",
        summary=f"Company merged into {survivor.name}",
        after_data={"survivor_company_id": str(survivor_id)},
    )
    return operation


def merge_record(
    db: Session,
    *,
    organization_id: UUID,
    entity_type: str,
    survivor_id: UUID,
    merged_id: UUID,
    actor_user_id: UUID,
) -> MergeOperation:
    if entity_type not in {"contact", "company"}:
        raise ValueError("Only contacts and companies can be merged")
    existing = db.scalar(
        select(MergeOperation)
        .where(
            MergeOperation.organization_id == organization_id,
            MergeOperation.entity_type == entity_type,
            MergeOperation.merged_id == merged_id,
        )
        .limit(1)
    )
    if existing is not None:
        raise ValueError("This record has already been merged")

    if entity_type == "contact":
        return _merge_contact(
            db,
            organization_id=organization_id,
            survivor_id=survivor_id,
            merged_id=merged_id,
            actor_user_id=actor_user_id,
        )
    return _merge_company(
        db,
        organization_id=organization_id,
        survivor_id=survivor_id,
        merged_id=merged_id,
        actor_user_id=actor_user_id,
    )
