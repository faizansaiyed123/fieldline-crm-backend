from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.models import Activity, Company, Contact, Opportunity, Task
from app.schemas.standout import (
    DataQualityResponse,
    DataQualitySummary,
    DuplicateCandidate,
    QualityIssue,
)
from app.services.business_rules import get_rule_value


def _contact_duplicates(db: Session, *, organization_id: UUID, limit: int = 50) -> list[DuplicateCandidate]:
    first = aliased(Contact)
    second = aliased(Contact)
    first_name = func.lower(func.concat(first.first_name, " ", first.last_name))
    second_name = func.lower(func.concat(second.first_name, " ", second.last_name))
    first_phone = func.regexp_replace(first.phone, r"D", "", "g")
    second_phone = func.regexp_replace(second.phone, r"D", "", "g")
    similarity = func.similarity(first_name, second_name)
    statement = (
        select(
            first.id.label("first_id"),
            second.id.label("second_id"),
            func.concat(first.first_name, " ", first.last_name).label("first_label"),
            func.concat(second.first_name, " ", second.last_name).label("second_label"),
            similarity.label("similarity"),
            first.email.label("first_email"),
            second.email.label("second_email"),
            first_phone.label("first_phone"),
            second_phone.label("second_phone"),
        )
        .where(first.organization_id == organization_id)
        .where(second.organization_id == organization_id)
        .where(first.deleted_at.is_(None))
        .where(second.deleted_at.is_(None))
        .where(first.id < second.id)
        .where(
            or_(
                and_(
                    first.email.is_not(None),
                    second.email.is_not(None),
                    func.lower(first.email) == func.lower(second.email),
                ),
                and_(
                    first.phone.is_not(None),
                    second.phone.is_not(None),
                    first_phone != "",
                    first_phone == second_phone,
                ),
                similarity >= 0.84,
            )
        )
        .order_by(similarity.desc(), first.id, second.id)
        .limit(limit)
    )
    rows = db.execute(statement).mappings().all()
    candidates: list[DuplicateCandidate] = []
    for row in rows:
        reasons: list[str] = []
        if row["first_email"] and row["second_email"] and row["first_email"].lower() == row["second_email"].lower():
            reasons.append("same email")
        if row["first_phone"] and row["second_phone"] and row["first_phone"] == row["second_phone"]:
            reasons.append("same phone")
        if float(row["similarity"] or 0) >= 0.84:
            reasons.append("very similar name")
        candidates.append(
            DuplicateCandidate(
                entity_type="contact",
                first_id=row["first_id"],
                second_id=row["second_id"],
                first_label=row["first_label"],
                second_label=row["second_label"],
                similarity=max(0.0, min(1.0, float(row["similarity"] or 0))),
                reasons=reasons,
            )
        )
    return candidates


def _company_duplicates(db: Session, *, organization_id: UUID, limit: int = 50) -> list[DuplicateCandidate]:
    first = aliased(Company)
    second = aliased(Company)
    first_name = func.lower(first.name)
    second_name = func.lower(second.name)
    first_phone = func.regexp_replace(first.phone, r"D", "", "g")
    second_phone = func.regexp_replace(second.phone, r"D", "", "g")
    similarity = func.similarity(first_name, second_name)
    statement = (
        select(
            first.id.label("first_id"),
            second.id.label("second_id"),
            first.name.label("first_label"),
            second.name.label("second_label"),
            similarity.label("similarity"),
            first.website.label("first_website"),
            second.website.label("second_website"),
            first_phone.label("first_phone"),
            second_phone.label("second_phone"),
        )
        .where(first.organization_id == organization_id)
        .where(second.organization_id == organization_id)
        .where(first.deleted_at.is_(None))
        .where(second.deleted_at.is_(None))
        .where(first.id < second.id)
        .where(
            or_(
                and_(
                    first.website.is_not(None),
                    second.website.is_not(None),
                    func.lower(first.website) == func.lower(second.website),
                ),
                and_(
                    first.phone.is_not(None),
                    second.phone.is_not(None),
                    first_phone != "",
                    first_phone == second_phone,
                ),
                similarity >= 0.86,
            )
        )
        .order_by(similarity.desc(), first.id, second.id)
        .limit(limit)
    )
    rows = db.execute(statement).mappings().all()
    candidates: list[DuplicateCandidate] = []
    for row in rows:
        reasons: list[str] = []
        if row["first_website"] and row["second_website"] and row["first_website"].lower() == row["second_website"].lower():
            reasons.append("same website")
        if row["first_phone"] and row["second_phone"] and row["first_phone"] == row["second_phone"]:
            reasons.append("same phone")
        if float(row["similarity"] or 0) >= 0.86:
            reasons.append("very similar company name")
        candidates.append(
            DuplicateCandidate(
                entity_type="company",
                first_id=row["first_id"],
                second_id=row["second_id"],
                first_label=row["first_label"],
                second_label=row["second_label"],
                similarity=max(0.0, min(1.0, float(row["similarity"] or 0))),
                reasons=reasons,
            )
        )
    return candidates


def build_data_quality_report(db: Session, *, organization_id: UUID) -> DataQualityResponse:
    now = datetime.now(UTC)
    contact_cutoff = now - timedelta(days=get_rule_value(db, organization_id=organization_id, key="contact_inactivity_days"))

    contact_duplicates = _contact_duplicates(db, organization_id=organization_id)
    company_duplicates = _company_duplicates(db, organization_id=organization_id)

    issues: list[QualityIssue] = []
    for candidate in contact_duplicates:
        issues.append(
            QualityIssue(
                code="duplicate_contact",
                entity_type="contact",
                entity_id=candidate.first_id,
                severity="high",
                title="Potential duplicate contact",
                detail=f"{candidate.first_label} matches {candidate.second_label}: {', '.join(candidate.reasons)}",
                fixable=True,
            )
        )
    for candidate in company_duplicates:
        issues.append(
            QualityIssue(
                code="duplicate_company",
                entity_type="company",
                entity_id=candidate.first_id,
                severity="high",
                title="Potential duplicate company",
                detail=f"{candidate.first_label} matches {candidate.second_label}: {', '.join(candidate.reasons)}",
                fixable=True,
            )
        )

    contact_last_activity = (
        select(func.max(Activity.occurred_at))
        .where(Activity.organization_id == organization_id, Activity.contact_id == Contact.id)
        .correlate(Contact)
        .scalar_subquery()
    )
    stale_contacts = db.scalars(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .where(Contact.deleted_at.is_(None))
        .where(Contact.lifecycle.in_(( "lead", "prospect" )))
        .where(func.coalesce(contact_last_activity, Contact.created_at) < contact_cutoff)
        .order_by(Contact.created_at.asc())
        .limit(50)
    ).all()
    for contact in stale_contacts:
        issues.append(
            QualityIssue(
                code="stale_contact",
                entity_type="contact",
                entity_id=contact.id,
                severity="medium",
                title="Stale lead or prospect",
                detail=f"{contact.first_name} {contact.last_name} has no recent activity",
                fixable=False,
            )
        )

    incomplete_contacts = db.scalars(
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .where(Contact.deleted_at.is_(None))
        .where(Contact.email.is_(None))
        .where(Contact.phone.is_(None))
        .limit(50)
    ).all()
    for contact in incomplete_contacts:
        issues.append(
            QualityIssue(
                code="missing_contact_channel",
                entity_type="contact",
                entity_id=contact.id,
                severity="medium",
                title="No contact channel",
                detail=f"{contact.first_name} {contact.last_name} has neither email nor phone",
                fixable=False,
            )
        )

    incomplete_opportunities = db.scalars(
        select(Opportunity)
        .where(Opportunity.organization_id == organization_id)
        .where(Opportunity.deleted_at.is_(None))
        .where(Opportunity.status == "open")
        .where(
            or_(
                Opportunity.expected_close_date.is_(None),
                and_(Opportunity.company_id.is_(None), Opportunity.contact_id.is_(None)),
            )
        )
        .limit(50)
    ).all()
    for opportunity in incomplete_opportunities:
        missing: list[str] = []
        if opportunity.expected_close_date is None:
            missing.append("expected close date")
        if opportunity.company_id is None and opportunity.contact_id is None:
            missing.append("company or contact")
        issues.append(
            QualityIssue(
                code="incomplete_opportunity",
                entity_type="opportunity",
                entity_id=opportunity.id,
                severity="medium",
                title="Opportunity missing key context",
                detail=f"{opportunity.name} is missing {', '.join(missing)}",
                fixable=False,
            )
        )

    overdue_tasks = db.scalars(
        select(Task)
        .where(Task.organization_id == organization_id)
        .where(Task.completed_at.is_(None))
        .where(Task.due_at.is_not(None))
        .where(Task.due_at < now)
        .order_by(Task.due_at.asc())
        .limit(50)
    ).all()
    for task in overdue_tasks:
        issues.append(
            QualityIssue(
                code="overdue_task",
                entity_type="task",
                entity_id=task.id,
                severity="high",
                title="Overdue task",
                detail=f"{task.title} is overdue and incomplete",
                fixable=False,
            )
        )

    issues.sort(key=lambda item: ({"high": 0, "medium": 1, "low": 2}[item.severity], item.code, str(item.entity_id)))
    issues = issues[:100]

    high = sum(item.severity == "high" for item in issues)
    medium = sum(item.severity == "medium" for item in issues)
    low = sum(item.severity == "low" for item in issues)
    summary = DataQualitySummary(
        total_issues=len(issues),
        high=high,
        medium=medium,
        low=low,
        duplicate_contacts=len(contact_duplicates),
        duplicate_companies=len(company_duplicates),
        incomplete_records=len(incomplete_contacts) + len(incomplete_opportunities),
        stale_contacts=len(stale_contacts),
        opportunity_issues=len(incomplete_opportunities),
        overdue_tasks=len(overdue_tasks),
    )
    return DataQualityResponse(
        generated_at=now,
        summary=summary,
        duplicate_candidates=contact_duplicates + company_duplicates,
        issues=issues,
    )
