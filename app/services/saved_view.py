from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Contact, SavedView
from app.services.audit import record_audit


def _visible_statement(
    *,
    organization_id: UUID,
    user_id: UUID,
):
    return select(SavedView).where(
        SavedView.organization_id == organization_id,
        or_(
            SavedView.shared.is_(True),
            SavedView.created_by_user_id == user_id,
        ),
    )


def list_saved_views(
    db: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
) -> list[SavedView]:
    return db.scalars(
        _visible_statement(organization_id=organization_id, user_id=user_id)
        .where(SavedView.resource == "contacts")
        .order_by(SavedView.shared.desc(), SavedView.name.asc())
    ).all()


def get_saved_view(
    db: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
    view_id: UUID,
) -> SavedView | None:
    return db.scalar(
        _visible_statement(organization_id=organization_id, user_id=user_id)
        .where(SavedView.id == view_id)
        .limit(1)
    )


def create_saved_view(
    db: Session,
    *,
    organization_id: UUID,
    user_id: UUID,
    name: str,
    shared: bool,
    definition: dict[str, object],
) -> SavedView:
    view = SavedView(
        organization_id=organization_id,
        created_by_user_id=user_id,
        resource="contacts",
        name=name,
        shared=shared,
        definition_version=1,
        definition=definition,
    )
    db.add(view)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=user_id,
        entity_type="saved_view",
        entity_id=view.id,
        action="created",
        summary=f"Created saved view {view.name}",
        after_data={"name": view.name, "shared": view.shared, "resource": view.resource},
    )
    return view


def can_manage_saved_view(view: SavedView, *, user_id: UUID, is_admin: bool) -> bool:
    return view.created_by_user_id == user_id or is_admin


def update_saved_view(
    db: Session,
    *,
    view: SavedView,
    actor_user_id: UUID,
    name: str | None,
    shared: bool | None,
    definition: dict[str, object] | None,
) -> SavedView:
    before = {
        "name": view.name,
        "shared": view.shared,
        "definition": view.definition,
    }
    if name is not None:
        view.name = name
    if shared is not None:
        view.shared = shared
    if definition is not None:
        view.definition = definition
        view.definition_version += 1
    db.flush()
    record_audit(
        db,
        organization_id=view.organization_id,
        actor_user_id=actor_user_id,
        entity_type="saved_view",
        entity_id=view.id,
        action="updated",
        summary=f"Updated saved view {view.name}",
        before_data=before,
        after_data={
            "name": view.name,
            "shared": view.shared,
            "definition": view.definition,
            "definition_version": view.definition_version,
        },
    )
    return view


def delete_saved_view(
    db: Session,
    *,
    view: SavedView,
    actor_user_id: UUID,
) -> None:
    view_id = view.id
    organization_id = view.organization_id
    db.delete(view)
    db.flush()
    record_audit(
        db,
        organization_id=organization_id,
        actor_user_id=actor_user_id,
        entity_type="saved_view",
        entity_id=view_id,
        action="deleted",
        summary=f"Deleted saved view {view.name}",
    )


def execute_contact_view(
    db: Session,
    *,
    view: SavedView,
    organization_id: UUID,
    limit: int,
    page: int,
) -> tuple[list[Contact], int]:
    definition = view.definition
    statement = (
        select(Contact)
        .where(Contact.organization_id == organization_id)
        .where(Contact.deleted_at.is_(None))
    )

    query = definition.get("query")
    if query:
        term = f"%{str(query).strip()}%"
        statement = statement.where(
            or_(
                Contact.first_name.ilike(term),
                Contact.last_name.ilike(term),
                Contact.email.ilike(term),
                Contact.phone.ilike(term),
                Contact.job_title.ilike(term),
            )
        )

    lifecycle = definition.get("lifecycle") or []
    if lifecycle:
        statement = statement.where(Contact.lifecycle.in_(lifecycle))

    company_id = definition.get("company_id")
    if company_id:
        statement = statement.where(Contact.company_id == UUID(str(company_id)))

    owner_user_id = definition.get("owner_user_id")
    if owner_user_id:
        statement = statement.where(Contact.owner_user_id == UUID(str(owner_user_id)))

    has_email = definition.get("has_email")
    if has_email is True:
        statement = statement.where(Contact.email.is_not(None))
    elif has_email is False:
        statement = statement.where(Contact.email.is_(None))

    sort = definition.get("sort", "updated_desc")
    if sort == "updated_asc":
        statement = statement.order_by(Contact.updated_at.asc(), Contact.id.asc())
    elif sort == "name_asc":
        statement = statement.order_by(
            func.lower(Contact.first_name).asc(),
            func.lower(Contact.last_name).asc(),
            Contact.id.asc(),
        )
    elif sort == "name_desc":
        statement = statement.order_by(
            func.lower(Contact.first_name).desc(),
            func.lower(Contact.last_name).desc(),
            Contact.id.desc(),
        )
    else:
        statement = statement.order_by(Contact.updated_at.desc(), Contact.id.desc())

    total = db.scalar(
        select(func.count()).select_from(statement.order_by(None).subquery())
    ) or 0
    items = db.scalars(
        statement.offset((page - 1) * limit).limit(limit)
    ).all()
    return items, total
