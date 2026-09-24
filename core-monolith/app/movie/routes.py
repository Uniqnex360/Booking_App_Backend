"""
FastAPI routes for Movie Module (Public, Partner & Admin Endpoints).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.auth.dependencies import require_role
from app.auth.interfaces import User as AuthUserDomain
from app.movie.dependencies import get_movie_service
from app.movie.exceptions import (
    InvalidLayoutGridHTTPError,
    MovieNotFoundHTTPError,
    MovieNotPublishedHTTPError,
    PartnerOwnershipHTTPError,
    ScreenLayoutLockedHTTPError,
    ScreenNotFoundHTTPError,
    SeatConflictHTTPError,
    SeatNotFoundHTTPError,
    ShowtimeNotFoundHTTPError,
    UnapprovedPartnerHTTPError,
    VenueNotFoundHTTPError,
)
from app.movie.interfaces import (
    MovieNotFoundError,
    MovieNotPublishedError,
    PartnerOwnershipError,
    ScreenLayoutLockedError,
    ScreenNotFoundError,
    SeatAlreadyBookedError,
    SeatNotFoundError,
    ShowtimeNotFoundError,
    UnapprovedPartnerError,
    VenueNotFoundError,
)
from app.movie.layout_parser import LayoutParseError
from app.movie.schemas import (
    AdminApplyLayoutRequest,
    ApplyLayoutRequest,
    AvailabilityResponse,
    BlockSeatsRequest,
    ContentStatusUpdateRequest,
    CreateMovieRequest,
    CreateScreenRequest,
    CreateShowtimeRequest,
    MovieDetailsResponse,
    MovieSummaryResponse,
    RowProjectionResponse,
    SeatMapResponse,
    SeatProjectionResponse,
    ShowtimeSlotResponse,
    UnblockSeatsRequest,
    UpdateMovieRequest,
    VenueShowtimesResponse,
)
from app.movie.services import MovieService
from app.partner.dependencies import required_approved_partner
from app.partner.interfaces import Partner
from app.shared.schemas import PaginatedResponse, PaginationMeta

movie_router = APIRouter(tags=["Movie"])


# ---------------------------------------------------------------------------
# Public Read Paths
# ---------------------------------------------------------------------------

@movie_router.get("/movies", response_model=PaginatedResponse[MovieSummaryResponse])
async def list_movies(
    city: str | None = Query(None),
    language: str | None = Query(None),
    format: str | None = Query(None),
    date: date | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    movie_service: MovieService = Depends(get_movie_service),
):
    items, total = await movie_service.list_movies(
        city=city,
        language=language,
        format=format,
        target_date=date,
        page=page,
        limit=limit,
    )
    responses = [
        MovieSummaryResponse(
            id=m.id,
            title=m.title,
            original_title=m.original_title,
            language=m.language,
            genre=m.genre,   
            duration_min=m.duration_min,
            certificate=m.certificate,
            release_date=m.release_date,
            poster_url=m.poster_url,
            banner_url=m.banner_url,
            status=m.status,
        )
        for m in items
    ]
    total_pages = (total + limit - 1) // limit if limit else 0
    return PaginatedResponse(
        data=responses,
        meta=PaginationMeta(total=total, page=page, limit=limit, total_pages=total_pages),
    )


@movie_router.get("/movies/{id}", response_model=MovieDetailsResponse)
async def get_movie_details(
    id: UUID,
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        dto = await movie_service.get_movie_details(id)
        return MovieDetailsResponse(
            id=dto.id,
            title=dto.title,
            original_title=dto.original_title,
            language=dto.language,
            duration_min=dto.duration_min,
            certificate=dto.certificate,
            release_date=dto.release_date,
            genre=dto.genre,
            poster_url=dto.poster_url,
            banner_url=dto.banner_url,  
            trailer_url=dto.trailer_url,
            synopsis=dto.synopsis,
            status=dto.status,
            venues=[
                VenueShowtimesResponse(
                    venue_id=v.venue_id,
                    venue_name=v.venue_name,
                    city=v.city,
                    address=v.address,
                    showtimes=[
                        ShowtimeSlotResponse(
                            id=st.id,
                            screen_id=st.screen_id,
                            screen_name=st.screen_name,
                            starts_at=st.starts_at,
                            language=st.language,
                            format=st.format,
                            status=st.status,
                        )
                        for st in v.showtimes
                    ],
                )
                for v in dto.venues
            ],
        )
    except MovieNotFoundError as exc:
        raise MovieNotFoundHTTPError(str(exc))


@movie_router.get("/showtimes/{id}/seat-map", response_model=SeatMapResponse)
async def get_seat_map(
    id: UUID,
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        dto = await movie_service.get_seat_map(id)
        return SeatMapResponse(
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
    except ShowtimeNotFoundError as exc:
        raise ShowtimeNotFoundHTTPError(str(exc))


@movie_router.get("/showtimes/{id}/availability", response_model=AvailabilityResponse)
async def get_showtime_availability(
    id: UUID,
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        dto = await movie_service.get_showtime_availability(id)
        return AvailabilityResponse(
            showtime_id=dto.showtime_id,
            total_seats=dto.total_seats,
            available_seats=dto.available_seats,
            booked_seats=dto.booked_seats,
            blocked_seats=dto.blocked_seats,
            locked_seats=getattr(dto, "locked_seats", 0),
        )
    except ShowtimeNotFoundError as exc:
        raise ShowtimeNotFoundHTTPError(str(exc))


# ---------------------------------------------------------------------------
# Partner Write Paths
# ---------------------------------------------------------------------------

@movie_router.post(
    "/partner/movies",
    response_model=MovieSummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_partner_movie(
    body: CreateMovieRequest,
    partner: Partner = Depends(required_approved_partner),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        dto = await movie_service.create_movie(
            title=body.title,
            original_title=body.original_title,
            language=body.language,
            duration_min=body.duration_min,
            certificate=body.certificate,
            partner_id=partner.id,
            poster_url=body.poster_url,
            synopsis=body.synopsis,
        )
        return MovieSummaryResponse(
            id=dto.id,
            title=dto.title,
            original_title=dto.original_title,
            language=dto.language,
            duration_min=dto.duration_min,
            certificate=dto.certificate,
            release_date=dto.release_date,
            poster_url=dto.poster_url,
            status=dto.status,
        )
    except UnapprovedPartnerError as exc:
        raise UnapprovedPartnerHTTPError(str(exc))


@movie_router.patch("/partner/movies/{id}", response_model=MovieSummaryResponse)
async def update_partner_movie(
    id: UUID,
    body: UpdateMovieRequest,
    partner: Partner = Depends(required_approved_partner),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        updates = body.model_dump(exclude_unset=True)
        dto = await movie_service.update_movie(
            movie_id=id, partner_id=partner.id, updates=updates
        )
        return MovieSummaryResponse(
            id=dto.id,
            title=dto.title,
            original_title=dto.original_title,
            language=dto.language,
            duration_min=dto.duration_min,
            certificate=dto.certificate,
            release_date=dto.release_date,
            poster_url=dto.poster_url,
            status=dto.status,
        )
    except MovieNotFoundError as exc:
        raise MovieNotFoundHTTPError(str(exc))
    except PartnerOwnershipError as exc:
        raise PartnerOwnershipHTTPError(str(exc))


@movie_router.post("/partner/screens", status_code=status.HTTP_201_CREATED)
async def create_partner_screen(
    body: CreateScreenRequest,
    partner: Partner = Depends(required_approved_partner),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        screen_id = await movie_service.create_screen(
            venue_id=body.venue_id,
            name=body.name,
            partner_id=partner.id,
        )
        return {"screen_id": screen_id, "status": "created"}
    except VenueNotFoundError as exc:
        raise VenueNotFoundHTTPError(str(exc))
    except PartnerOwnershipError as exc:
        raise PartnerOwnershipHTTPError(str(exc))


@movie_router.patch("/partner/screens/{id}/layout")
async def apply_screen_layout(
    id: UUID,
    body: ApplyLayoutRequest,
    partner: Partner = Depends(required_approved_partner),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        total_seats = await movie_service.apply_screen_layout(
            screen_id=id,
            text_grid=body.text_grid,
            default_price_paise=body.default_price_paise,
            section=body.section,
            is_admin_override=False,
        )
        return {"screen_id": id, "total_seats": total_seats, "status": "updated"}
    except ScreenNotFoundError as exc:
        raise ScreenNotFoundHTTPError(str(exc))
    except ScreenLayoutLockedError as exc:
        raise ScreenLayoutLockedHTTPError(str(exc))
    except LayoutParseError as exc:
        raise InvalidLayoutGridHTTPError(str(exc))


@movie_router.post("/admin/screens/{id}/layout")
async def admin_override_screen_layout(
    id: UUID,
    body: AdminApplyLayoutRequest,
    admin_user: AuthUserDomain = Depends(require_role("ADMIN")),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        total_seats = await movie_service.apply_screen_layout(
            screen_id=id,
            text_grid=body.text_grid,
            default_price_paise=body.default_price_paise,
            section=body.section,
            is_admin_override=True,
        )
        return {
            "screen_id": id,
            "total_seats": total_seats,
            "admin_override": True,
            "reason": body.override_reason,
        }
    except ScreenNotFoundError as exc:
        raise ScreenNotFoundHTTPError(str(exc))
    except LayoutParseError as exc:
        raise InvalidLayoutGridHTTPError(str(exc))


@movie_router.post("/partner/showtimes", status_code=status.HTTP_201_CREATED)
async def create_partner_showtime(
    body: CreateShowtimeRequest,
    partner: Partner = Depends(required_approved_partner),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        st_id = await movie_service.create_showtime(
            screen_id=body.screen_id,
            movie_id=body.movie_id,
            starts_at=body.starts_at,
            language=body.language,
            format=body.format,
            partner_id=partner.id,
        )
        return {"showtime_id": st_id, "status": "created"}
    except MovieNotPublishedError as exc:
        raise MovieNotPublishedHTTPError(str(exc))
    except MovieNotFoundError as exc:
        raise MovieNotFoundHTTPError(str(exc))
    except ScreenNotFoundError as exc:
        raise ScreenNotFoundHTTPError(str(exc))


@movie_router.patch("/partner/showtimes/{id}/cancel")
async def cancel_partner_showtime(
    id: UUID,
    partner: Partner = Depends(required_approved_partner),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        await movie_service.cancel_showtime(
            showtime_id=id, partner_id=partner.id
        )
        return {"showtime_id": id, "status": "CANCELLED"}
    except ShowtimeNotFoundError as exc:
        raise ShowtimeNotFoundHTTPError(str(exc))
    except PartnerOwnershipError as exc:
        raise PartnerOwnershipHTTPError(str(exc))


@movie_router.patch("/partner/showtimes/{id}/seats/block")
async def block_showtime_seats(
    id: UUID,
    body: BlockSeatsRequest,
    partner: Partner = Depends(required_approved_partner),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        await movie_service.block_seats(
            showtime_id=id, seat_ids=body.seat_ids, reason=body.reason
        )
        return {"showtime_id": id, "blocked_seats": len(body.seat_ids)}
    except ShowtimeNotFoundError as exc:
        raise ShowtimeNotFoundHTTPError(str(exc))
    except SeatNotFoundError as exc:
        raise SeatNotFoundHTTPError(str(exc))
    except SeatAlreadyBookedError as exc:
        raise SeatConflictHTTPError(str(exc))


@movie_router.patch("/partner/showtimes/{id}/seats/unblock")
async def unblock_showtime_seats(
    id: UUID,
    body: UnblockSeatsRequest,
    partner: Partner = Depends(required_approved_partner),
    movie_service: MovieService = Depends(get_movie_service),
):
    try:
        await movie_service.unblock_seats(showtime_id=id, seat_ids=body.seat_ids)
        return {"showtime_id": id, "unblocked_seats": len(body.seat_ids)}
    except ShowtimeNotFoundError as exc:
        raise ShowtimeNotFoundHTTPError(str(exc))


# ---------------------------------------------------------------------------
# Admin Moderation Path
# ---------------------------------------------------------------------------

