"""
Movie & Showtime Service — pure domain logic.

Boundary Contract Checklist:
- ZERO imports from fastapi or starlette
- ZERO imports from schemas.py, exceptions.py, models.py, repository.py
- Imports ONLY from interfaces.py and app.shared
- Raises ONLY domain exceptions
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from app.movie.interfaces import (
    IMovieRepository,
    MovieDetailsDTO,
    MovieNotFoundError,
    MovieNotPublishedError,
    MovieSummaryDTO,
    SeatMapDTO,
    ShowtimeAvailabilityDTO,
    ShowtimeNotFoundError,
)
from app.movie.layout_parser import parse_text_grid


class MovieService:

    async def release_expired_locks(self, booking_id: UUID) -> int:
        return await self._repo.release_expired_locks(booking_id)


    async def create_venue(
        self, *, name: str, city: str, partner_id: UUID, address: str | None = None, latitude: float | None = None, longitude: float | None = None, timezone: str = "Asia/Kolkata"
    ):
        return await self._repo.create_venue(
            name=name, city=city, partner_id=partner_id, address=address, latitude=latitude, longitude=longitude, timezone=timezone
        )

    def __init__(self, movie_repo: IMovieRepository) -> None:
        self._repo = movie_repo

    # --- Read Paths ---

    async def list_movies(
        self,
        *,
        city: str | None = None,
        language: str | None = None,
        format: str | None = None,
        target_date: date | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[MovieSummaryDTO], int]:
        return await self._repo.list_movies(
            city=city,
            language=language,
            format=format,
            target_date=target_date,
            page=page,
            limit=limit,
        )

    async def get_movie_details(self, movie_id: UUID) -> MovieDetailsDTO:
        movie = await self._repo.get_movie_details(movie_id)
        if movie is None:
            raise MovieNotFoundError(f"Movie '{movie_id}' not found")
        return movie

    async def get_seat_map(self, showtime_id: UUID) -> SeatMapDTO:
        seat_map = await self._repo.get_seat_map(showtime_id)
        if seat_map is None:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")
        return seat_map

    async def get_showtime_availability(
        self, showtime_id: UUID
    ) -> ShowtimeAvailabilityDTO:
        availability = await self._repo.get_showtime_availability(showtime_id)
        if availability is None:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")
        return availability

    # --- Partner Write Paths ---

    async def create_movie(
        self,
        *,
        title: str,
        original_title: str | None,
        language: str,
        duration_min: int,
        certificate: str,
        partner_id: UUID,
        poster_url: str | None = None,
        synopsis: str | None = None,
    ) -> MovieSummaryDTO:
        return await self._repo.create_movie(
            title=title,
            original_title=original_title,
            language=language,
            duration_min=duration_min,
            certificate=certificate,
            partner_id=partner_id,
            poster_url=poster_url,
            synopsis=synopsis,
        )

    async def update_movie(
        self, movie_id: UUID, partner_id: UUID, updates: dict
    ) -> MovieSummaryDTO:
        return await self._repo.update_movie(movie_id, partner_id, updates)

    async def update_movie_status(
        self, movie_id: UUID, new_status: str
    ) -> MovieSummaryDTO:
        return await self._repo.update_movie_status(movie_id, new_status)

    async def create_screen(
        self, venue_id: UUID, name: str, partner_id: UUID
    ) -> UUID:
        return await self._repo.create_screen(venue_id, name, partner_id)

    async def apply_screen_layout(
        self,
        screen_id: UUID,
        text_grid: str,
        default_price_paise: int,
        section: str | None = None,
        is_admin_override: bool = False,
    ) -> int:
        parsed_rows = parse_text_grid(
            grid_text=text_grid,
            default_price_paise=default_price_paise,
            section=section,
        )
        return await self._repo.apply_screen_layout(
            screen_id, parsed_rows, is_admin_override=is_admin_override
        )

    async def create_showtime(
        self,
        *,
        screen_id: UUID,
        movie_id: UUID,
        starts_at: datetime,
        language: str,
        format: str,
        partner_id: UUID,
    ) -> UUID:
        movie = await self._repo.get_movie_details(movie_id)
        if not movie:
            raise MovieNotPublishedError(
                f"Movie '{movie_id}' must be PUBLISHED before showtimes can be created."
            )
        return await self._repo.create_showtime(
            screen_id=screen_id,
            movie_id=movie_id,
            starts_at=starts_at,
            language=language,
            format=format,
            partner_id=partner_id,
        )

    async def cancel_showtime(
        self, showtime_id: UUID, partner_id: UUID
    ) -> bool:
        return await self._repo.cancel_showtime(showtime_id, partner_id)

    async def block_seats(
        self, showtime_id: UUID, seat_ids: list[UUID], reason: str
    ) -> bool:
        return await self._repo.block_seats(showtime_id, seat_ids, reason)

    async def unblock_seats(
        self, showtime_id: UUID, seat_ids: list[UUID]
    ) -> bool:
        return await self._repo.unblock_seats(showtime_id, seat_ids)