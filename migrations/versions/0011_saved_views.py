"""Create tenant-scoped saved search views."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011_saved_views"
down_revision = "0010_import_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "saved_views",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("resource", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("shared", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("definition_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("definition", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_saved_views_org_resource_shared",
        "saved_views",
        ["organization_id", "resource", "shared"],
    )
    op.create_index(
        "ix_saved_views_org_creator",
        "saved_views",
        ["organization_id", "created_by_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_saved_views_org_creator", table_name="saved_views")
    op.drop_index("ix_saved_views_org_resource_shared", table_name="saved_views")
    op.drop_table("saved_views")
