from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Activity, Company, Contact, Opportunity, Task
from app.schemas.standout import GraphEdge, GraphNode, RelationshipGraphResponse


def build_relationship_graph(
    db: Session,
    *,
    organization_id: UUID,
    contact_id: UUID,
) -> RelationshipGraphResponse:
    contact = db.scalar(
        select(Contact)
        .where(
            Contact.organization_id == organization_id,
            Contact.id == contact_id,
            Contact.deleted_at.is_(None),
        )
        .limit(1)
    )
    if contact is None:
        raise ValueError("Contact not found")

    nodes: dict[str, GraphNode] = {
        f"contact:{contact.id}": GraphNode(
            id=f"contact:{contact.id}",
            type="contact",
            label=f"{contact.first_name} {contact.last_name}",
            meta={"email": contact.email, "lifecycle": contact.lifecycle},
        )
    }
    edges: list[GraphEdge] = []

    if contact.company_id:
        company = db.scalar(
            select(Company)
            .where(Company.organization_id == organization_id, Company.id == contact.company_id)
            .where(Company.deleted_at.is_(None))
            .limit(1)
        )
        if company:
            node_id = f"company:{company.id}"
            nodes[node_id] = GraphNode(id=node_id, type="company", label=company.name, meta={"website": company.website})
            edges.append(GraphEdge(id=f"contact-company:{contact.id}", source=f"contact:{contact.id}", target=node_id, label="works at"))

    opportunities = db.scalars(
        select(Opportunity)
        .where(Opportunity.organization_id == organization_id, Opportunity.contact_id == contact.id)
        .where(Opportunity.deleted_at.is_(None))
        .order_by(Opportunity.updated_at.desc())
        .limit(25)
    ).all()
    for opportunity in opportunities:
        node_id = f"opportunity:{opportunity.id}"
        nodes[node_id] = GraphNode(
            id=node_id,
            type="opportunity",
            label=opportunity.name,
            meta={"status": opportunity.status, "amount": str(opportunity.amount) if opportunity.amount is not None else None},
        )
        edges.append(GraphEdge(id=f"contact-opp:{opportunity.id}", source=f"contact:{contact.id}", target=node_id, label="involved in"))

    tasks = db.scalars(
        select(Task)
        .where(Task.organization_id == organization_id, Task.contact_id == contact.id)
        .order_by(Task.due_at.desc().nullslast(), Task.id.desc())
        .limit(20)
    ).all()
    for task in tasks:
        node_id = f"task:{task.id}"
        nodes[node_id] = GraphNode(
            id=node_id,
            type="task",
            label=task.title,
            meta={"priority": task.priority, "due_at": task.due_at.isoformat() if task.due_at else None},
        )
        edges.append(GraphEdge(id=f"contact-task:{task.id}", source=f"contact:{contact.id}", target=node_id, label="has task"))

    activities = db.scalars(
        select(Activity)
        .where(Activity.organization_id == organization_id, Activity.contact_id == contact.id)
        .order_by(Activity.occurred_at.desc())
        .limit(20)
    ).all()
    for activity in activities:
        node_id = f"activity:{activity.id}"
        nodes[node_id] = GraphNode(
            id=node_id,
            type="activity",
            label=activity.title,
            meta={"type": activity.activity_type, "occurred_at": activity.occurred_at.isoformat()},
        )
        edges.append(GraphEdge(id=f"contact-activity:{activity.id}", source=f"contact:{contact.id}", target=node_id, label="activity"))

    return RelationshipGraphResponse(contact_id=contact.id, nodes=list(nodes.values()), edges=edges)
