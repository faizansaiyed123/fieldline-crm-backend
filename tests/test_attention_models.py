from app.db.base import Base
from app.models import Contact, Opportunity, Task


def test_attention_indexes_are_registered() -> None:
    task_indexes = {index.name for index in Base.metadata.tables[Task.__tablename__].indexes}
    contact_indexes = {index.name for index in Base.metadata.tables[Contact.__tablename__].indexes}
    opportunity_indexes = {
        index.name for index in Base.metadata.tables[Opportunity.__tablename__].indexes
    }

    assert "ix_tasks_org_attention" in task_indexes
    assert "ix_contacts_org_attention" in contact_indexes
    assert "ix_opportunities_org_attention" in opportunity_indexes
