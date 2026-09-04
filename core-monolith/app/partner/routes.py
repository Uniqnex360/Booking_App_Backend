import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, Request


from app.shared.response import success_response
from app.shared.pagination import calculate_pagination_meta
from app.shared.exceptions import DuplicateEntityError, EntityNotFoundError, RepositoryError


from app.auth.interfaces import User as AuthUserDomain, IUserRepository, INotificationService
from app.auth.dependencies import (
    get_current_user, 
    require_role, 
    get_user_repo, 
    get_notification_service
)


from app.partner.dependencies import get_partner_service
from app.partner.services import PartnerService
from app.partner.interfaces import PartnerStatus, InvalidStatusTransitionError
from app.partner.schemas import PartnerRegisterRequest, PartnerStatusUpdateRequest
from app.partner.exceptions import (
    PartnerNotFoundHTTP, 
    DuplicatePartnerHTTP, 
    InvalidStatusTransitionHTTP,
    PartnerRepositoryHTTP 
)

router = APIRouter(prefix="/partner", tags=["Partner"])

@router.post('/register', status_code=201)
async def register_partner(
    data: PartnerRegisterRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service)
):
    try:
        partner = await service.register_partner(current_user.id, data.model_dump())
        return success_response(
            data=partner, 
            message="Partner registration submitted. Awaiting admin approval.",
            code=201
        )
    except DuplicateEntityError as e:
        raise DuplicatePartnerHTTP(str(e))
    except RepositoryError as e:
        raise PartnerRepositoryHTTP(str(e))

@router.get('/me')
async def get_my_partner_profile(
    current_user: AuthUserDomain = Depends(get_current_user),
    service: PartnerService = Depends(get_partner_service)
):
    try:
        partner = await service.get_partner_by_user_id(current_user.id)
        return success_response(data=partner, message="Profile fetched successfully.")
    except EntityNotFoundError:
        raise PartnerNotFoundHTTP()
    except RepositoryError as e:
        raise PartnerRepositoryHTTP(str(e))

@router.get('/admin')
async def list_partners_admin(
    status: Optional[str] = Query(None),
    partner_type: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    admin_user: AuthUserDomain = Depends(require_role(['ADMIN'])),
    service: PartnerService = Depends(get_partner_service)
):
    try:
        items, total = await service.list_partners(status, partner_type, page, limit)
        meta = calculate_pagination_meta(total, page, limit)
        
        return success_response(
            data={"partners": items, "pagination": meta},
            message="Partners list fetched successfully."
        )
    except RepositoryError as e:
        raise PartnerRepositoryHTTP(str(e))
