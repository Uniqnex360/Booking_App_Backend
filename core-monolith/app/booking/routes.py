from __future__ import annotations

from app.movie.dependencies import get_movie_service
from app.movie.services import MovieService
from datetime import date
from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse
from app.auth.dependencies import get_current_user
from app.auth.interfaces import User as AuthUserDomain
from app.providers.base import HoldAlreadyCommitted
from app.booking.dependencies import get_booking_service, get_movie_booking_service
from app.booking.interfaces import (
    BookingNotCancellableError,
    BookingNotFoundError,
    EventNotBookableError,
    IllegalBookingTransition,
    QuantityExceedsMaxError,
    SalesClosedError,
    ShowtimeDisabledError,
    ShowtimeNotFoundError,
    ShowtimeNotProviderError,
    SoldOutError,
    TierInactiveError,
    ValidationError,
)
from app.booking.movie_service import MovieBookingService
from app.booking.schemas import (
    BookingCreateRequest,
    CommitBookingRequest,
    ProviderHoldCreateRequest,
)
from app.booking.services import BookingService
from app.movie.interfaces import SeatAlreadyBookedError, SeatNotFoundError
from app.providers.base import (
    HoldExpiredRemote,
    ProviderUnavailable,
    SeatUnavailableRemote,
)
from app.shared.response import error_response, success_response
router = APIRouter(tags=["bookings"])



@router.post("/bookings/hold", status_code=status.HTTP_201_CREATED)
async def create_provider_hold(
    payload: ProviderHoldCreateRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    current_user: AuthUserDomain = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    if not idempotency_key:
        return error_response(
            error_type="VALIDATION_ERROR",
            message="Idempotency-Key header is required",
            code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    try:
        booking = await booking_service.create_hold(
            user_id=current_user.id,
            showtime_id=payload.showtime_id,
            seat_ids=payload.seat_ids,
            idem_key=idempotency_key,
        )
        return success_response(
            data={
                "id": str(booking.id),
                "status": booking.status.value,
                "held_until": booking.held_until.isoformat() if booking.held_until else None,
                "total_paise": booking.total_paise,
                "currency": booking.currency,
                "seats": booking.seat_refs or payload.seat_ids,
            },
            message="Hold created successfully",
            code=status.HTTP_201_CREATED,
        )
    except ValidationError as exc:
        return error_response("VALIDATION_ERROR", str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
    except SeatUnavailableRemote as exc:
        return error_response(
            "SEAT_UNAVAILABLE_REMOTE",
            str(exc),
            status.HTTP_409_CONFLICT,
            details=exc.seats,
        )
    except ShowtimeNotFoundError as exc:
        return error_response("SHOWTIME_NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)
    except ShowtimeNotProviderError as exc:
        return error_response("SHOWTIME_NOT_PROVIDER", str(exc), status.HTTP_400_BAD_REQUEST)
    except ShowtimeDisabledError as exc:
        return error_response("SHOWTIME_DISABLED", str(exc), status.HTTP_400_BAD_REQUEST)
    except ProviderUnavailable as exc:
        return error_response("PROVIDER_UNAVAILABLE", str(exc), status.HTTP_502_BAD_GATEWAY)
@router.post("/bookings/{booking_id}/commit", status_code=status.HTTP_200_OK)
async def commit_booking(
    booking_id: UUID,
    payload: CommitBookingRequest | None = None,
    current_user: AuthUserDomain = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    payment_ref = payload.payment_ref if payload else None
    try:
        booking = await booking_service.commit_booking(
            user_id=current_user.id,
            booking_id=booking_id,
            payment_ref=payment_ref,
        )
        return success_response(
            data={
                "id": str(booking.id),
                "status": booking.status.value,
                "ref_code": booking.ref_code,
                "barcode": booking.barcode,
                "total_paise": booking.total_paise,
                "currency": booking.currency,
            },
            message="Booking confirmed successfully",
            code=status.HTTP_200_OK,
        )
    except BookingNotFoundError:
        return error_response("BOOKING_NOT_FOUND", "Booking not found", status.HTTP_404_NOT_FOUND)
    except IllegalBookingTransition as exc:
        return error_response("ILLEGAL_BOOKING_TRANSITION", str(exc), status.HTTP_409_CONFLICT)
    except HoldExpiredRemote as exc:
        return error_response("HOLD_EXPIRED", str(exc), status.HTTP_409_CONFLICT)
    except HoldAlreadyCommitted as exc:
        return error_response("HOLD_ALREADY_COMMITTED", str(exc), status.HTTP_409_CONFLICT)
    except ProviderUnavailable as exc:
        return error_response("PROVIDER_UNAVAILABLE", str(exc), status.HTTP_502_BAD_GATEWAY)
@router.delete("/bookings/hold/{booking_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_provider_hold(
    booking_id: UUID,
    current_user: AuthUserDomain = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    try:
        await booking_service.cancel_hold(
            user_id=current_user.id, booking_id=booking_id
        )
        return JSONResponse(status_code=status.HTTP_204_NO_CONTENT, content=None)
    except BookingNotFoundError:
        return error_response("BOOKING_NOT_FOUND", "Booking not found", status.HTTP_404_NOT_FOUND)
    except IllegalBookingTransition as exc:
        return error_response("ILLEGAL_BOOKING_TRANSITION", str(exc), status.HTTP_409_CONFLICT)
@router.get("/bookings/{booking_id}", status_code=status.HTTP_200_OK)
async def get_booking_details(
    booking_id: UUID,
    current_user: AuthUserDomain = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    try:
        booking = await booking_service.get_booking_for_user(
            user_id=current_user.id, booking_id=booking_id
        )
        return success_response(
            data={
                "id": str(booking.id),
                "status": booking.status.value,
                "total_paise": booking.total_paise,
                "currency": booking.currency,
                "ref_code": booking.ref_code,
                "barcode": booking.barcode,
                "held_until": booking.held_until.isoformat() if booking.held_until else None,
                "created_at": booking.created_at.isoformat() if booking.created_at else None,
            },
            message="Booking fetched successfully",
        )
    except BookingNotFoundError:
        return error_response("BOOKING_NOT_FOUND", "Booking not found", status.HTTP_404_NOT_FOUND)



@router.get("/showtimes/{showtime_id}/seat-map", status_code=status.HTTP_200_OK)
async def get_showtime_seat_map(
    showtime_id: UUID,
    booking_service: BookingService = Depends(get_booking_service),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        # Check if the showtime is provider-backed
        try:
            st, _, _ = await booking_service._resolve_provider_and_showtime(showtime_id)
        except ShowtimeNotProviderError:
            # Fall back directly to the legacy self-hosted Movie router handler logic
            dto = await movie_service.get_seat_map(showtime_id)
            from app.movie.schemas import SeatMapResponse as MovieSeatMapResponse, RowProjectionResponse, SeatProjectionResponse
            return MovieSeatMapResponse(
                showtime_id=dto.showtime_id,
                movie_id=dto.movie_id,
                movie_title=dto.movie_title,
                venue_name=dto.venue_name,
                screen_name=dto.screen_name,
                starts_at=dto.starts_at,
                format=dto.format,
                language=dto.language,
                rows=[
                    RowProjectionResponse(
                        row_id=r.row_id,
                        label=r.label,
                        section=r.section,
                        price_paise=r.price_paise,
                        seats=[
                            SeatProjectionResponse(
                                seat_id=s.seat_id,
                                number=s.number,
                                code=s.code,
                                x=s.x,
                                label=s.label,
                                status=s.status.value,
                                price_paise=s.price_paise,
                            )
                            for s in r.seats
                        ],
                    )
                    for r in dto.rows
                ],
            )

        seat_map, is_available = await booking_service.get_provider_seat_map(showtime_id)
        if not is_available or seat_map is None:
            return {
                "status": "success",
                "code": 200,
                "data": {
                    "showtime_id": str(showtime_id),
                    "seats": [],
                    "code": "SOURCE_UNAVAILABLE",
                },
                "message": "Provider upstream is currently unavailable",
            }
        return success_response(
            data={
                "showtime_id": seat_map.showtime_ref,
                "movie_title": seat_map.movie_title,
                "screen_name": seat_map.screen_name,
                "cinema_name": seat_map.cinema_name,
                "starts_at": seat_map.starts_at.isoformat(),
                "fetched_at": seat_map.fetched_at.isoformat(),
                "seats": [
                    {
                        "seat_ref": s.seat_ref,
                        "row_label": s.row_label,
                        "number": s.seat_number,
                        "code": s.seat_code,
                        "price_paise": s.price_paise,
                        "is_available": s.is_available,
                    }
                    for s in seat_map.seats
                ],
            }
        )
    except ShowtimeNotFoundError as exc:
        return error_response("SHOWTIME_NOT_FOUND", str(exc), status.HTTP_404_NOT_FOUND)
    except Exception as exc:
        return {
            "status": "success",
            "code": 200,
            "data": {
                "showtime_id": str(showtime_id),
                "seats": [],
                "code": "SOURCE_UNAVAILABLE",
            },
            "message": f"Provider upstream error: {exc}",
        }



@router.get("/partner/reconcile", status_code=status.HTTP_200_OK)
async def reconcile(
    date_param: date = Query(..., alias="date"),
    current_user: AuthUserDomain = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    result = await booking_service.reconcile_bookings(date_param)
    return success_response(data=result, message="Reconciliation report generated")



@router.post("/bookings", status_code=status.HTTP_201_CREATED)
async def create_legacy_booking(
    payload: BookingCreateRequest,
    current_user: AuthUserDomain = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
    movie_booking_service: MovieBookingService = Depends(get_movie_booking_service),
):
    try:
        if payload.showtime_id and payload.seat_ids:
            booking = await movie_booking_service.create_booking(
                user_id=current_user.id,
                showtime_id=payload.showtime_id,
                seat_ids=payload.seat_ids,
                idempotency_key=payload.idempotency_key,
            )
        else:
            booking = await booking_service.create_booking(
                user_id=current_user.id,
                tier_id=payload.tier_id,
                quantity=payload.quantity,
                idempotency_key=payload.idempotency_key,
            )
    except SeatAlreadyBookedError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except SoldOutError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except (EventNotBookableError, TierInactiveError, SalesClosedError, ValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except QuantityExceedsMaxError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (ShowtimeNotFoundError, SeatNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"booking": {"id": str(booking.id)}}
@router.patch("/bookings/{booking_id}/cancel")
async def cancel_legacy_booking(
    booking_id: UUID,
    current_user: AuthUserDomain = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
    movie_booking_service: MovieBookingService = Depends(get_movie_booking_service),
):
    try:
        booking = await movie_booking_service.cancel_booking(booking_id, current_user.id)
    except BookingNotFoundError:
        try:
            booking = await booking_service.cancel_booking(booking_id, current_user.id)
        except BookingNotFoundError:
            raise HTTPException(status_code=404, detail="Booking not found")
        except BookingNotCancellableError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
    except BookingNotCancellableError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"booking": {"id": str(booking.id), "status": "CANCELLED"}}

@router.get("/bookings", status_code=status.HTTP_200_OK)
async def list_my_bookings(
    current_user: AuthUserDomain = Depends(get_current_user),
    booking_service: BookingService = Depends(get_booking_service),
):
    from sqlalchemy import select
    from app.booking.models import BookingModel
    from app.movie.models import Showtime, Movie, Screen, Venue
    from app.event.models import EventORM, TicketCategoryORM
    import json

    session = booking_service.session
    stmt = (
        select(
            BookingModel,
            Showtime,
            Movie,
            Screen,
            Venue,
            EventORM,
            TicketCategoryORM,
        )
        .outerjoin(Showtime, BookingModel.showtime_id == Showtime.id)
        .outerjoin(Movie, Showtime.movie_id == Movie.id)
        .outerjoin(Screen, Showtime.screen_id == Screen.id)
        .outerjoin(Venue, Screen.venue_id == Venue.id)
        .outerjoin(EventORM, BookingModel.event_id == EventORM.id)
        .outerjoin(TicketCategoryORM, BookingModel.tier_id == TicketCategoryORM.id)
        .where(BookingModel.user_id == current_user.id)
        .order_by(BookingModel.created_at.desc())
    )

    res = await session.execute(stmt)
    rows = res.all()

    enriched_bookings = []
    for b, st, movie, screen, venue, event, tier in rows:
        # Determine Title, Venue, Location, Image, and Date
        if movie:
            title = movie.title
            venue_name = f"{venue.name} • {screen.name}" if (venue and screen) else (venue.name if venue else "Cinema Hall")
            location = venue.city if venue else "Kochi"
            image_url = movie.poster_url or "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=600&auto=format&fit=crop&q=80"
            booking_date = st.starts_at.isoformat() if st else b.created_at.isoformat()
            
            # Count seats from seat_refs_json or default 1
            seat_count = 1
            if b.seat_refs_json:
                try:
                    seat_count = len(json.loads(b.seat_refs_json))
                except Exception:
                    seat_count = 1
            guests = seat_count
        elif event:
            title = event.title
            venue_name = event.venue_name or "Event Venue"
            location = event.venue_address or "Kochi"
            image_url = event.cover_image_url if hasattr(event, "cover_image_url") and event.cover_image_url else "https://images.pexels.com/photos/13230484/pexels-photo-13230484.jpeg?auto=compress&cs=tinysrgb&h=400&w=600"
            booking_date = b.created_at.isoformat()
            guests = b.quantity or 1
        else:
            title = "Cinema Booking" if b.booking_type == "MOVIE" else "Experience Booking"
            venue_name = "PVR Cinemas" if b.provider_id else "Venue"
            location = "Kochi"
            image_url = "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=600&auto=format&fit=crop&q=80"
            booking_date = b.created_at.isoformat()
            guests = 1

        total_rupees = b.total_paise // 100

        enriched_bookings.append({
            "id": str(b.id),
            "user_id": str(b.user_id),
            "type": b.booking_type or ("MOVIE" if b.showtime_id else "EVENT"),
            "title": title,
            "venue": venue_name,
            "location": location,
            "booking_date": booking_date,
            "guests": guests,
            "total_price": total_rupees,
            "status": b.status,
            "image_url": image_url,
            "ref_code": b.ref_code,
            "barcode": b.barcode,
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })

    return success_response(
        data=enriched_bookings,
        message="User bookings fetched successfully",
    )
