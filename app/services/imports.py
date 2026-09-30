import csv
import io
import re
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Contact, ImportJob, ImportRow
from app.services.audit import record_audit

MAX_FILE_SIZE = 5 * 1024 * 1024
MAX_ROWS = 5000
MAX_ERROR_ROWS = 200
ALLOWED_HEADERS = {
    "first_name",
    "last_name",
    "email",
    "phone",
    "job_title",
    "lifecycle",
}
REQUIRED_HEADERS = {"first_name", "last_name"}


def _normalize_phone(value: str | None) -> str:
    return re.sub(r"\D", "", value or "")


def _value(value: str | None) -> str | None:
    value = " ".join((value or "").split())
    return value or None


def _parse_csv(content: bytes) -> tuple[list[str], list[dict[str, str]]]:
    if len(content) > MAX_FILE_SIZE:
        raise ValueError("CSV file exceeds the 5 MB limit")
    if b"\x00" in content:
        raise ValueError("CSV contains invalid NUL bytes")

    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be valid UTF-8") from exc

    try:
        reader = csv.DictReader(io.StringIO(text, newline=""))
        headers = [header.strip().lower() for header in (reader.fieldnames or [])]
    except csv.Error as exc:
        raise ValueError("Invalid CSV format") from exc

    if not headers:
        raise ValueError("CSV must contain a header row")
    if len(set(headers)) != len(headers):
        raise ValueError("CSV contains duplicate headers")
    missing = REQUIRED_HEADERS - set(headers)
    if missing:
        raise ValueError(f"CSV is missing required headers: {', '.join(sorted(missing))}")
    unknown = set(headers) - ALLOWED_HEADERS
    if unknown:
        raise ValueError(f"CSV contains unsupported headers: {', '.join(sorted(unknown))}")

    rows: list[dict[str, str]] = []
    for row in reader:
        normalized = {key.strip().lower(): (value or "") for key, value in row.items() if key is not None}
        rows.append(normalized)

    if len(rows) > MAX_ROWS:
        raise ValueError("CSV exceeds the 5,000 row limit")

    return headers, rows


def _validate_row(row: dict[str, str]) -> tuple[dict[str, object] | None, list[str]]:
    try:
        from app.schemas.contact import ContactCreate

        payload = ContactCreate(
            first_name=_value(row.get("first_name")) or "",
            last_name=_value(row.get("last_name")) or "",
            email=_value(row.get("email")),
            phone=_value(row.get("phone")),
            job_title=_value(row.get("job_title")),
            lifecycle=_value(row.get("lifecycle")) or "lead",
        )
        normalized = payload.model_dump(mode="json", exclude_none=True)
        normalized.pop("company_id", None)
        return normalized, []
    except Exception as exc:
        message = str(exc)
        if hasattr(exc, "errors"):
            messages = []
            for error in exc.errors():
                location = ".".join(str(part) for part in error.get("loc", ()))
                detail = error.get("msg", "invalid value")
                messages.append(f"{location}: {detail}" if location else detail)
            return None, messages
        return None, [message]


def _existing_contact_keys(
    db: Session,
    organization_id: UUID,
) -> tuple[set[str], set[str]]:
    contacts = db.execute(
        select(Contact.email, Contact.phone)
        .where(Contact.organization_id == organization_id)
        .where(Contact.deleted_at.is_(None))
    ).all()
    emails = {email.lower() for email, _ in contacts if email}
    phones = {_normalize_phone(phone) for _, phone in contacts if phone and _normalize_phone(phone)}
    return emails, phones


def _current_duplicate_errors(
    db: Session,
    organization_id: UUID,
    normalized_rows: list[tuple[int, dict[str, object] | None]],
) -> dict[int, list[str]]:
    existing_emails, existing_phones = _existing_contact_keys(db, organization_id)
    seen_emails: set[str] = set()
    seen_phones: set[str] = set()
    errors: dict[int, list[str]] = {}

    for row_number, data in normalized_rows:
        if not data:
            continue
        row_errors: list[str] = []
        email = str(data.get("email", "")).lower() or None
        phone = _normalize_phone(str(data.get("phone", ""))) or None

        if email:
            if email in existing_emails:
                row_errors.append("email already exists in this organization")
            elif email in seen_emails:
                row_errors.append("email is duplicated in this import")
            seen_emails.add(email)

        if phone:
            if phone in existing_phones:
                row_errors.append("phone already exists in this organization")
            elif phone in seen_phones:
                row_errors.append("phone is duplicated in this import")
            seen_phones.add(phone)

        if row_errors:
            errors[row_number] = row_errors

    return errors


def _preview_response(job: ImportJob, rows: list[ImportRow]) -> dict[str, Any]:
    errors = [
        {"row_number": row.row_number, "errors": [item["message"] for item in row.errors]}
        for row in rows
        if row.status != "valid"
    ]
    return {
        "id": job.id,
        "status": job.status,
        "filename": job.filename,
        "total_rows": job.total_rows,
        "valid_rows": job.valid_rows,
        "invalid_rows": job.invalid_rows,
        "committed_rows": job.committed_rows,
        "created_at": job.created_at or datetime.now(UTC),
        "completed_at": job.completed_at,
        "errors": errors[:MAX_ERROR_ROWS],
        "errors_truncated": len(errors) > MAX_ERROR_ROWS,
    }


def preview_contact_import(
    db: Session,
    *,
    organization_id: UUID,
    actor_user_id: UUID,
    filename: str,
    content_type: str | None,
    content: bytes,
) -> tuple[ImportJob, list[ImportRow]]:
    _, csv_rows = _parse_csv(content)
    job = ImportJob(
        organization_id=organization_id,
        created_by_user_id=actor_user_id,
        entity_type="contact",
        status="preview_ready",
        filename=(filename or "contacts.csv")[:255],
        content_type=content_type,
        file_size_bytes=len(content),
        total_rows=len(csv_rows),
    )
    db.add(job)
    db.flush()

    normalized_rows: list[tuple[int, dict[str, object] | None]] = []
    row_objects: list[ImportRow] = []

    for offset, raw in enumerate(csv_rows, start=2):
        normalized, errors = _validate_row(raw)
        row = ImportRow(
            import_job_id=job.id,
            row_number=offset,
            status="valid" if not errors else "invalid",
            raw_data=raw,
            normalized_data=normalized,
            errors=[{"message": error} for error in errors],
        )
        db.add(row)
        row_objects.append(row)
        normalized_rows.append((offset, normalized))

    duplicate_errors = _current_duplicate_errors(
        db,
        organization_id,
        normalized_rows,
    )
    for row in row_objects:
        if row.row_number not in duplicate_errors:
            continue
        row.status = "invalid"
        row.errors = row.errors + [
            {"message": message} for message in duplicate_errors[row.row_number]
        ]

    job.valid_rows = sum(row.status == "valid" for row in row_objects)
    job.invalid_rows = len(row_objects) - job.valid_rows
    db.flush()
    return job, row_objects


def get_import_job(
    db: Session,
    *,
    organization_id: UUID,
    job_id: UUID,
) -> ImportJob | None:
    return db.scalar(
        select(ImportJob)
        .where(ImportJob.organization_id == organization_id)
        .where(ImportJob.id == job_id)
        .limit(1)
    )


def _refresh_job_state(job: ImportJob, rows: list[ImportRow]) -> None:
    job.valid_rows = sum(row.status == "valid" for row in rows)
    job.invalid_rows = len(rows) - job.valid_rows


def commit_contact_import(
    db: Session,
    *,
    job: ImportJob,
    actor_user_id: UUID,
    dry_run: bool,
) -> tuple[int, int]:
    if job.status != "preview_ready":
        raise ValueError("Import job is not ready to commit")

    rows = db.scalars(
        select(ImportRow)
        .where(ImportRow.import_job_id == job.id)
        .order_by(ImportRow.row_number)
        .with_for_update()
    ).all()
    _refresh_job_state(job, rows)

    if job.invalid_rows:
        raise ValueError("Import contains validation errors; fix them before commit")

    normalized_rows = [(row.row_number, row.normalized_data) for row in rows]
    duplicate_errors = _current_duplicate_errors(
        db,
        job.organization_id,
        normalized_rows,
    )
    if duplicate_errors:
        for row in rows:
            if row.row_number in duplicate_errors:
                row.status = "invalid"
                row.errors = [{"message": message} for message in duplicate_errors[row.row_number]]
        _refresh_job_state(job, rows)
        raise ValueError("Import changed since preview; new duplicates were detected")

    if dry_run:
        return job.valid_rows, 0

    now = datetime.now(UTC)
    job.status = "committing"
    job.started_at = now
    db.flush()

    contacts: list[Contact] = []
    for row in rows:
        data = dict(row.normalized_data or {})
        contact = Contact(
            organization_id=job.organization_id,
            owner_user_id=actor_user_id,
            first_name=str(data["first_name"]),
            last_name=str(data["last_name"]),
            email=str(data["email"]).lower() if data.get("email") else None,
            phone=str(data["phone"]) if data.get("phone") else None,
            job_title=str(data["job_title"]) if data.get("job_title") else None,
            lifecycle=str(data.get("lifecycle", "lead")),
        )
        contacts.append(contact)

    db.add_all(contacts)
    db.flush()

    job.status = "completed"
    job.committed_rows = len(contacts)
    job.completed_at = datetime.now(UTC)
    record_audit(
        db,
        organization_id=job.organization_id,
        actor_user_id=actor_user_id,
        entity_type="import_job",
        entity_id=job.id,
        action="completed",
        summary=f"Imported {len(contacts)} contacts from {job.filename}",
        after_data={
            "status": job.status,
            "total_rows": job.total_rows,
            "committed_rows": job.committed_rows,
        },
    )
    return 0, len(contacts)
