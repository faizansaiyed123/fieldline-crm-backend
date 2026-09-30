import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.company import Company
    from app.models.opportunity import Opportunity
    from app.models.organization import Organization


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(40), nullable=True)
    job_title: Mapped[str | None] = mapped_column(String(160), nullable=True)
    lifecycle: Mapped[str] = mapped_column(String(32), nullable=False, default="lead")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship()
    company: Mapped["Company | None"] = relationship(back_populates="contacts")
    opportunities: Mapped[list["Opportunity"]] = relationship(back_populates="contact")

    __table_args__ = (
        Index("ix_contacts_org_owner_active", "organization_id", "owner_user_id", "deleted_at"),
        Index("ix_contacts_org_email_active", "organization_id", func.lower(email), postgresql_where=deleted_at.is_(None)),
        Index(
            "ix_contacts_org_name_active",
            "organization_id",
            func.lower(first_name),
            func.lower(last_name),
            postgresql_where=deleted_at.is_(None),
        ),
        Index(
            "ix_contacts_org_phone_active",
            "organization_id",
            func.regexp_replace(phone, r"\D", "", "g"),
            postgresql_where=deleted_at.is_(None),
        ),
        Index("ix_contacts_org_attention", "organization_id", "lifecycle", "deleted_at"),
    )
