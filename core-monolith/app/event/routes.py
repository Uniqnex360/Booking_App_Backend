from fastapi import APIRouter, Depends, Query
import uuid
from typing import Optional
from app.event.schemas import EventCreateRequest, EventResponse, EventDetailResponse, EventStatusUpdateRequest
from app.event.dependencies import get_event_service
from app.event.services import EventService
from app.partner.dependencies import required_approved_partner
from app.partner.interfaces import Partner, PartnerType
from app.shared.response import success_response
from app.shared.exceptions import ForbiddenError
from app.auth.dependencies import require_role
from app.auth.interfaces import User as AuthUserDomain

router = APIRouter(prefix="/events", tags=["Event"])

@router.post("", status_code=201)
async def create_event(
    data: EventCreateRequest,
    partner: Partner = Depends(required_approved_partner),
    service: EventService = Depends(get_event_service)
):
    if partner.partner_type != PartnerType.EVENT_ORGANISER:
        raise ForbiddenError("Only event organisers can create events")
    
    event = await service.create_event(partner.id, data.model_dump())
    return success_response(data=event, message="Event created as DRAFT", code=201)

@router.get("")
async def list_events(
    city: Optional[str] = None,
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    service: EventService = Depends(get_event_service)
):
    events, total = await service.list_public(city=city, page=page, limit=limit)
    return success_response(data={"items": events, "total": total})

# @router.get("/pending")
# async def get_pending_events(
#     admin: AuthUserDomain = Depends(require_role(["ADMIN"])),
#     service: EventService = Depends(get_event_service)
# ):
#     events = await service.list_pending_events() 
#     return success_response(data={"items": events}, message="Pending events fetched")
@router.post("/{event_id}/status")
async def update_event_status(
    event_id: uuid.UUID,
    data: EventStatusUpdateRequest,
    partner: Partner = Depends(required_approved_partner),
    service: EventService = Depends(get_event_service)
):
    event = await service.update_status(partner.id, event_id, data.status, data.cancellation_reason)
    return success_response(data=event, message=f"Status updated to {data.status}")
@router.get("/me")
async def get_my_events(
    partner: Partner = Depends(required_approved_partner),
    service: EventService = Depends(get_event_service)
):
    events = await service.list_for_partner(partner.id)
    return success_response(data={"items": events}, message="My events fetched")