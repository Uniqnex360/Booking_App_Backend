from fastapi import APIRouter, Depends
from typing import Optional
import uuid

from app.auth.dependencies import get_user_repo
from app.auth.interfaces import IUserRepository
from app.admin.dependencies import require_admin
from app.auth.interfaces import User as AuthUserDomain
from app.partner.dependencies import get_partner_service
from app.shared.pagination import calculate_pagination_meta

from app.partner.services import PartnerService

from app.shared.response import success_response
from app.partner.schemas import PartnerStatusUpdateRequest
from app.auth.dependencies import require_role
from app.auth.interfaces import INotificationService
from app.auth.dependencies import get_notification_service
from app.partner.interfaces import PartnerStatus
from app.event.schemas import EventStatusUpdateRequest
from app.event.dependencies import get_event_service
from app.shared.exceptions import EntityNotFoundError
from app.partner.exceptions import InvalidStatusTransitionHTTP, PartnerNotFoundHTTP, PartnerRepositoryHTTP
from app.auth.exceptions import RepositoryError
from app.partner.interfaces import InvalidStatusTransitionError
from app.admin.services import AdminService
from app.admin.dependencies import get_admin_service

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
    dependencies=[Depends(require_admin)] 
)


@router.get("/partners")
async def list_partners(
    status: Optional[str] = None,
    partner_type: Optional[str] = None,
    page: int = 1,
    limit: int = 10,
    service: PartnerService = Depends(get_partner_service) 
):
    items, total = await service.list_partners(status, partner_type, page, limit)
    meta = calculate_pagination_meta(total, page, limit)
    return success_response(data={"partners": items, "pagination": meta}, message="Partners fetched")

@router.patch('/partners/{partner_id}/status')
async def update_partner_status_admin(
    partner_id: uuid.UUID,
    data: PartnerStatusUpdateRequest,
    admin_user: AuthUserDomain = Depends(require_role(["ADMIN"])),
    service: PartnerService = Depends(get_partner_service),
    user_repo: IUserRepository = Depends(get_user_repo),
    notification_service: INotificationService = Depends(get_notification_service)
):
    try:
        
        partner = await service.update_partner_status(
            partner_id=partner_id,
            new_status=data.status,
            admin_id=admin_user.id,
            rejection_reason=data.rejection_reason
        )

        
        target_user = await user_repo.get_by_id(partner.user_id)
        
        
        if target_user and target_user.email:
            try:
                if data.status == PartnerStatus.APPROVED:
                    subject = "Your Partner Application is Approved!"
                    body = (
                        f"Hello {partner.contact_name},\n\n"
                        f"Good news! Your business '{partner.business_name}' has been approved. "
                        f"You can now log in to the Partner Dashboard."
                    )
                    await notification_service.send_email(target_user.email, subject, body)
                    
                elif data.status == PartnerStatus.REJECTED:
                    subject = "Update on your Partner Application"
                    body = (
                        f"Hello {partner.contact_name},\n\n"
                        f"Unfortunately, your application for '{partner.business_name}' was rejected.\n\n"
                        f"Reason: {data.rejection_reason}\n\n"
                        f"You can update your details and re-apply."
                    )
                    await notification_service.send_email(target_user.email, subject, body)
            except Exception as e:
                print(f"Notification Error: {e}")

        return success_response(data=partner, message="Partner status updated successfully.")

    except EntityNotFoundError:
        raise PartnerNotFoundHTTP()
    except InvalidStatusTransitionError as e:
        raise InvalidStatusTransitionHTTP(str(e))
    except RepositoryError as e:
        raise PartnerRepositoryHTTP(str(e))
@router.get("/content/pending")
async def get_pending_content(
    service: AdminService = Depends(get_admin_service) # Correct provider
):
    events = await service.list_pending_events()
    return success_response(data={"items": events}, message="Pending events fetched")

@router.patch("/content/{event_id}/status")
async def update_event_status(
    event_id: uuid.UUID,
    data: EventStatusUpdateRequest,
    service: AdminService = Depends(get_admin_service) # Correct provider
):
    event = await service.approve_or_reject_event( # Correct method name
        event_id, 
        data.status, 
        data.cancellation_reason

    )
    return success_response(data=event, message="Event status updated")