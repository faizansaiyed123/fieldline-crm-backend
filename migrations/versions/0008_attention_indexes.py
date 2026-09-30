"""Add indexes for deterministic attention queries."""

import sqlalchemy as sa
from alembic import op

revision = "0008_attention_indexes"
down_revision = "0007_timeline_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_tasks_org_attention",
        "tasks",
        ["organization_id", "completed_at", "due_at"],
    )
    op.create_index(
        "ix_contacts_org_attention",
        "contacts",
        ["organization_id", "lifecycle", "deleted_at"],
    )
    op.create_index(
        "ix_opportunities_org_attention",
        "opportunities",
        ["organization_id", "status", "expected_close_date", "deleted_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_opportunities_org_attention", table_name="opportunities")
    op.drop_index("ix_contacts_org_attention", table_name="contacts")
    op.drop_index("ix_tasks_org_attention", table_name="tasks")
