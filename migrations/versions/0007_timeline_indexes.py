"""Add timeline lookup index for contact-linked tasks."""

from alembic import op

revision = "0007_timeline_indexes"
down_revision = "0006_activity_tasks_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_tasks_org_contact_due",
        "tasks",
        ["organization_id", "contact_id", "due_at", "completed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_tasks_org_contact_due", table_name="tasks")
