from fastapi import APIRouter, Depends

from app.auth.authorization import require_membership, require_roles
from app.auth.schemas import MembershipResponse
from app.models import Membership, MembershipRole

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/{organization_id}/membership", response_model=MembershipResponse)
def get_membership(
    membership: Membership = Depends(require_membership),
) -> MembershipResponse:
    return MembershipResponse.model_validate(membership)


@router.get("/{organization_id}/admin-access", response_model=MembershipResponse)
def admin_access(
    membership: Membership = Depends(require_roles(MembershipRole.OWNER, MembershipRole.ADMIN)),
) -> MembershipResponse:
    return MembershipResponse.model_validate(membership)
