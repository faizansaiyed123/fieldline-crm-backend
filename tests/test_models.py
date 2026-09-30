from app.db.base import Base
from app.models import AuthRateLimit, AuthSession, Membership, MembershipRole, Organization, User


def test_identity_tables_are_registered() -> None:
    identity_tables = {
        "organizations",
        "users",
        "organization_memberships",
        "auth_sessions",
        "auth_rate_limits",
    }
    assert identity_tables <= set(Base.metadata.tables)


def test_membership_role_values_are_stable() -> None:
    assert [role.value for role in MembershipRole] == ["owner", "admin", "member"]


def test_identity_constraints_exist() -> None:
    users = Base.metadata.tables[User.__tablename__]
    organizations = Base.metadata.tables[Organization.__tablename__]
    memberships = Base.metadata.tables[Membership.__tablename__]
    sessions = Base.metadata.tables[AuthSession.__tablename__]
    rate_limits = Base.metadata.tables[AuthRateLimit.__tablename__]

    assert any(index.unique for index in users.indexes)
    assert any(
        constraint.name == "uq_membership_org_user" for constraint in memberships.constraints
    )
    assert any(
        "slug" in [column.name for column in constraint.columns]
        for constraint in organizations.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    )
    assert any(index.name == "ix_memberships_org_role" for index in memberships.indexes)
    assert any(index.name == "ix_auth_sessions_user_active" for index in sessions.indexes)
    assert any(
        constraint.name == "uq_auth_rate_scope_key" for constraint in rate_limits.constraints
    )
