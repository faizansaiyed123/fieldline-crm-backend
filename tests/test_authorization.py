import pytest
from fastapi import HTTPException

from app.auth.authorization import require_roles
from app.models import Membership, MembershipRole


def test_owner_and_admin_roles_are_accepted() -> None:
    dependency = require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)

    assert dependency(Membership(role=MembershipRole.OWNER)).role is MembershipRole.OWNER
    assert dependency(Membership(role=MembershipRole.ADMIN)).role is MembershipRole.ADMIN


def test_member_is_rejected_from_admin_dependency() -> None:
    dependency = require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)

    with pytest.raises(HTTPException) as exc_info:
        dependency(Membership(role=MembershipRole.MEMBER))

    assert exc_info.value.status_code == 403
