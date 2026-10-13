from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import (
    get_current_user,
    get_current_user_optional,
    get_notification_service,
    get_token_service,
)
from app.auth.interfaces import INotificationService, ITokenService, User as AuthUserDomain
from app.core.database import get_db
from app.notification.models import UserDeviceTokenModel, UserNotificationModel
from app.notification.service import (
    create_user_notification,
    format_relative_time,
    subscribe_user_stream,
    unsubscribe_user_stream,
)
from app.shared.response import success_response
from app.shared.timeutil import utcnow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class DeviceTokenRequest(BaseModel):
    fcm_token: str
    platform: str = "web"


@router.get("", status_code=status.HTTP_200_OK)
async def list_my_notifications(
    limit: int = Query(30, ge=1, le=100),
    current_user: AuthUserDomain = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(UserNotificationModel)
        .where(UserNotificationModel.user_id == current_user.id)
        .order_by(UserNotificationModel.created_at.desc())
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()

    items = [
        {
            "id": str(r.id),
            "title": r.title,
            "description": r.description,
            "time": format_relative_time(r.created_at),
            "read": bool(r.is_read),
            "type": r.type if r.type in ("booking", "offer", "update") else "booking",
            "link": r.link,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]

    unread_count = sum(1 for item in items if not item["read"])
    return success_response(
        data={
            "items": items,
            "notifications": items,
            "unread_count": unread_count,
        }
    )


@router.get("/stream")
async def stream_my_notifications(
    request: Request,
    token: Optional[str] = Query(default=None),
    optional_user: Optional[AuthUserDomain] = Depends(get_current_user_optional),
    token_service: ITokenService = Depends(get_token_service),
):
    user_id: Optional[UUID] = optional_user.id if optional_user else None
    if not user_id and token:
        try:
            payload = token_service.decode_token(token, token_type="access")
            user_id = UUID(str(payload.get("sub")))
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token")
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")

    queue = subscribe_user_stream(user_id)

    async def event_generator():
        try:
            yield ": connected\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=20.0)
                    yield f"data: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            unsubscribe_user_stream(user_id, queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.patch("/{notification_id}/read", status_code=status.HTTP_200_OK)
async def mark_notification_read(
    notification_id: UUID,
    current_user: AuthUserDomain = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(UserNotificationModel)
        .where(
            UserNotificationModel.id == notification_id,
            UserNotificationModel.user_id == current_user.id,
        )
        .values(is_read=True)
    )
    await db.commit()
    return success_response(data={"id": str(notification_id), "read": True})


@router.post("/read-all", status_code=status.HTTP_200_OK)
async def mark_all_notifications_read(
    current_user: AuthUserDomain = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        update(UserNotificationModel)
        .where(
            UserNotificationModel.user_id == current_user.id,
            UserNotificationModel.is_read.is_(False),
        )
        .values(is_read=True)
    )
    await db.commit()
    return success_response(data={"marked_all_read": True})


@router.delete("", status_code=status.HTTP_200_OK)
async def clear_my_notifications(
    current_user: AuthUserDomain = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.execute(
        delete(UserNotificationModel).where(
            UserNotificationModel.user_id == current_user.id
        )
    )
    await db.commit()
    return success_response(data={"cleared": True})


@router.post("/devices", status_code=status.HTTP_200_OK)
async def register_device_token(
    body: DeviceTokenRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    token_str = body.fcm_token.strip()
    if not token_str:
        raise HTTPException(status_code=400, detail="fcm_token is required")

    existing = (
        await db.execute(
            select(UserDeviceTokenModel).where(
                UserDeviceTokenModel.fcm_token == token_str
            )
        )
    ).scalar_one_or_none()

    now = utcnow()
    if existing:
        existing.user_id = current_user.id
        existing.platform = body.platform[:32]
        existing.updated_at = now
    else:
        db.add(
            UserDeviceTokenModel(
                id=uuid.uuid4(),
                user_id=current_user.id,
                fcm_token=token_str,
                platform=body.platform[:32],
                created_at=now,
                updated_at=now,
            )
        )
    await db.commit()
    return success_response(data={"registered": True})


@router.post("/send-reminders", status_code=status.HTTP_200_OK)
async def trigger_upcoming_show_reminders(
    db: AsyncSession = Depends(get_db),
    notification_service: INotificationService = Depends(get_notification_service),
):
    """
    Scans CONFIRMED movie bookings starting within the next 3 hours and sends
    idempotent in-app + email reminders.
    """
    from app.booking.models import BookingModel
    from app.movie.models import Movie, Screen, Showtime, Venue

    now = utcnow()
    window_end = now + timedelta(hours=3)

    stmt = (
        select(BookingModel, Showtime, Movie, Screen, Venue)
        .join(Showtime, BookingModel.showtime_id == Showtime.id)
        .join(Movie, Showtime.movie_id == Movie.id)
        .outerjoin(Screen, Showtime.screen_id == Screen.id)
        .outerjoin(Venue, Screen.venue_id == Venue.id)
        .where(
            BookingModel.status == "CONFIRMED",
            Showtime.starts_at > now,
            Showtime.starts_at <= window_end,
        )
    )
    rows = (await db.execute(stmt)).all()
    sent_count = 0

    for booking, showtime, movie, screen, venue in rows:
        ref_key = f"reminder:showtime:{booking.id}"
        if booking.user_id:
            existing = (
                await db.execute(
                    select(UserNotificationModel).where(
                        UserNotificationModel.user_id == booking.user_id,
                        UserNotificationModel.reference_key == ref_key,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                continue

        venue_name = venue.name if venue else "Cinema"
        screen_name = screen.name if screen else "Screen"
        starts_str = showtime.starts_at.strftime("%I:%M %p")
        title = f"Showtime Reminder: {movie.title} 🍿"
        desc = (
            f"Your show at {venue_name} ({screen_name}) starts at {starts_str}. "
            f"Ref: {booking.ref_code or str(booking.id)[:8].upper()}."
        )

        if booking.user_id:
            await create_user_notification(
                session=db,
                user_id=booking.user_id,
                title=title,
                description=desc,
                notif_type="booking",
                link=f"/bookings/{booking.id}",
                reference_key=ref_key,
                commit=True,
            )
            sent_count += 1

        if booking.contact_email:
            try:
                await notification_service.send_email(
                    email=booking.contact_email,
                    subject=f"Reminder: {movie.title} starts soon! ({booking.ref_code})",
                    body=(
                        f"<div style='font-family:sans-serif;max-width:520px;margin:auto;padding:24px;border:1px solid #eee;border-radius:12px;'>"
                        f"<h2 style='color:#7B1E3D;margin-top:0;'>🍿 Your Movie Starts Soon!</h2>"
                        f"<p>{desc}</p>"
                        f"<p style='font-size:13px;color:#555;'>Please arrive 15 minutes early and carry your QR e-ticket.</p>"
                        f"</div>"
                    ),
                    content_type="html",
                )
            except Exception as exc:
                logger.warning("Reminder email failed for booking %s: %s", booking.id, exc)

    return success_response(data={"reminders_sent": sent_count})

