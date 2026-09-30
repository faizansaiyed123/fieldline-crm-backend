from app.db.base import Base
from app.models import Company, Contact, Opportunity, PipelineStage


def test_crm_tables_are_registered() -> None:
    assert {
        Company.__tablename__,
        Contact.__tablename__,
        Opportunity.__tablename__,
        PipelineStage.__tablename__,
    } <= set(Base.metadata.tables)


def test_company_has_active_name_uniqueness_index() -> None:
    indexes = Base.metadata.tables[Company.__tablename__].indexes
    assert any(index.name == "uq_companies_org_name_active" and index.unique for index in indexes)


def test_contact_has_search_indexes() -> None:
    indexes = Base.metadata.tables[Contact.__tablename__].indexes
    names = {index.name for index in indexes}
    assert "ix_contacts_org_name_active" in names
    assert "ix_contacts_org_email_active" in names


def test_opportunity_has_pipeline_and_close_date_indexes() -> None:
    indexes = Base.metadata.tables[Opportunity.__tablename__].indexes
    names = {index.name for index in indexes}
    assert "ix_opportunities_org_stage" in names
    assert "ix_opportunities_org_close_date" in names


def test_pipeline_stage_enforces_org_scoped_names() -> None:
    constraints = Base.metadata.tables[PipelineStage.__tablename__].constraints
    assert any(
        constraint.name == "uq_pipeline_stage_org_name" for constraint in constraints
    )
