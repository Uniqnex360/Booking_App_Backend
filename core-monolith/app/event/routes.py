import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query, status

from app.event.schemas import (
    EventCreateRequest,EventUpdateRequest,
    EventStatusUpdateRequest,
)
from app.event.dependencies import get_event_service
from app.event.services import EventService
from app.partner.dependencies import required_approved_partner
from app.partner.interfaces import Partner
from app.shared.response import success_response
from app.shared.exceptions import ForbiddenError

router = APIRouter(prefix="/events", tags=["Event"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_event(
    data: EventCreateRequest,
    partner: Partner = Depends(required_approved_partner),
    service: EventService = Depends(get_event_service)
):
    p_type = partner.partner_type.value if hasattr(partner.partner_type, "value") else str(partner.partner_type)
    if p_type.lower() not in ("event_organiser", "event_organizer"):
        raise ForbiddenError("Only event organisers can create events")
    
    event = await service.create_event(partner.id, data.model_dump())
    return success_response(data=event, message="Event created as PENDING_APPROVAL", code=201)


@router.get("")
async def list_events(
    city: Optional[str] = None,
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    limit: int = Query(10, le=100),
    service: EventService = Depends(get_event_service)
):
    events, total = await service.list_public(city=city, category=category, page=page, limit=limit)
    return success_response(data={"items": events, "total": total})


@router.get("/me")
async def get_my_events(
    partner: Partner = Depends(required_approved_partner),
    service: EventService = Depends(get_event_service)
):
    events = await service.list_for_partner(partner.id)
    return success_response(data={"items": events}, message="My events fetched")


@router.get("/{event_id}")
async def get_event_by_id(
    event_id: uuid.UUID,
    service: EventService = Depends(get_event_service)
):
    event = await service.get_event_details(event_id)
    return success_response(data=event, message="Event details fetched")

@router.patch("/{event_id}")
async def update_event(
    event_id: uuid.UUID,
    data: EventUpdateRequest,
    partner: Partner = Depends(required_approved_partner),
    service: EventService = Depends(get_event_service)
):
    event = await service.update_event(
        partner.id, event_id, data.model_dump(exclude_unset=True)
    )
    return success_response(data=event, message="Event updated successfully")
@router.delete("/{event_id}")
async def delete_or_cancel_event(
    event_id: uuid.UUID,
    reason: Optional[str] = Query(None),
    partner: Partner = Depends(required_approved_partner),
    service: EventService = Depends(get_event_service)
):
    event = await service.delete_or_cancel_event(partner.id, event_id, reason)
    return success_response(data=event, message="Event cancelled successfully")


@router.post("/{event_id}/status")
async def update_event_status(
    event_id: uuid.UUID,
    data: EventStatusUpdateRequest,
    partner: Partner = Depends(required_approved_partner),
    service: EventService = Depends(get_event_service)
):
    event = await service.update_status(partner.id, event_id, data.status, data.cancellation_reason)
    return success_response(data=event, message=f"Status updated to {data.status}")
