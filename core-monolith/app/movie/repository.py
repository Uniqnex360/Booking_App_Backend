"""
SQLAlchemy repository implementation for Movie Module read/write operations.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from app.shared.timeutil import utcnow
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.movie.interfaces import (
    MovieDetailsDTO,
    MovieNotFoundError,
    MovieSummaryDTO,
    PartnerOwnershipError,
    RowProjectionDTO,
    ScreenLayoutLockedError,
    ScreenNotFoundError,
    SeatAlreadyBookedError,
    SeatMapDTO,
    SeatNotFoundError,
    SeatProjectionDTO,
    SeatStatus,
    ShowtimeAvailabilityDTO,
    ShowtimeNotFoundError,
    ShowtimeSlotDTO,
    VenueNotFoundError,
    VenueShowtimesDTO,
)
from app.movie.models import (
    MovieSoldCount,
    Movie,
    MovieStatus,
    Screen,
    ScreenRow,
    Seat,
    SeatState,
    SeatStateStatus,
    Showtime,
    ShowtimeStatus,
    Venue,
)


class MovieRepository:

    async def release_expired_locks(self, booking_id: UUID) -> int:
        stmt = delete(SeatState).where(SeatState.booking_id == booking_id, SeatState.status == "LOCKED")
        res = await self._session.execute(stmt)
        await self._session.commit()
        return res.rowcount


    async def create_venue(
        self, *, name: str, city: str, partner_id: UUID, address: str | None = None, latitude: float | None = None, longitude: float | None = None, timezone: str = "Asia/Kolkata"
    ) -> Venue:
        v = Venue(
            id=uuid.uuid4(),
            name=name,
            city=city,
            address=address,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            partner_id=partner_id,
        )
        self._session.add(v)
        await self._session.commit()
        return v

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # -----------------------------------------------------------------------
    # Public Read Paths
    # -----------------------------------------------------------------------

    # async def list_movies(
    #     self,
    #     *,
    #     city: str | None = None,
    #     language: str | None = None,
    #     format: str | None = None,
    #     target_date: date | None = None,
    #     page: int = 1,
    #     limit: int = 20,
    # ) -> tuple[list[MovieSummaryDTO], int]:
    #     stmt = select(Movie).where(Movie.status == MovieStatus.PUBLISHED.value)

    #     if language:
    #         stmt = stmt.where(Movie.language == language)

    #     # always join to showtimes
    #         stmt = stmt.join(Showtime, Showtime.movie_id == Movie.id).join(
    #             Screen, Showtime.screen_id == Screen.id
    #         )
    #         if city:
    #             stmt = stmt.join(Venue, Screen.venue_id == Venue.id).where(
    #                 Venue.city == city
    #             )
    #         if format:
    #             stmt = stmt.where(Showtime.format == format)
    #         if target_date:
    #             tz = ZoneInfo("Asia/Kolkata")
    #             start_dt = datetime.combine(target_date, time.min, tzinfo=tz).astimezone(ZoneInfo("UTC"))
    #             end_dt = datetime.combine(target_date, time.max, tzinfo=tz).astimezone(ZoneInfo("UTC"))
    #             stmt = stmt.where(Showtime.starts_at.between(start_dt, end_dt))

    #     stmt = stmt.distinct()

    #     count_stmt = select(func.count()).select_from(stmt.subquery())
    #     total = (await self._session.execute(count_stmt)).scalar() or 0

    #     offset = (page - 1) * limit
    #     stmt = stmt.order_by(Movie.created_at.desc()).offset(offset).limit(limit)

    #     result = await self._session.execute(stmt)
    #     movies = result.scalars().all()

    #     dtos = [
    #         MovieSummaryDTO(
    #             id=m.id,
    #             title=m.title,
    #             genre=m.genre, 
    #             original_title=m.original_title,
    #             language=m.language,
    #             duration_min=m.duration_min,
    #             certificate=m.certificate,
    #             release_date=m.release_date,
    #             poster_url=m.poster_url,
    #             status=m.status,
    #         )
    #         for m in movies
    #     ]
    #     return dtos, total
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
        stmt = select(Movie).where(Movie.status == MovieStatus.PUBLISHED.value)

        if language:
            stmt = stmt.where(Movie.language == language)

        stmt = stmt.join(Showtime, Showtime.movie_id == Movie.id).join(
            Screen, Showtime.screen_id == Screen.id
        )
        stmt = stmt.where(Showtime.starts_at > utcnow())

        if city:
            stmt = stmt.join(Venue, Screen.venue_id == Venue.id).where(
                Venue.city == city
            )
        if format:
            stmt = stmt.where(Showtime.format == format)
        if target_date:
            tz = ZoneInfo("Asia/Kolkata")
            start_dt = datetime.combine(target_date, time.min, tzinfo=tz).astimezone(ZoneInfo("UTC"))
            end_dt = datetime.combine(target_date, time.max, tzinfo=tz).astimezone(ZoneInfo("UTC"))
            stmt = stmt.where(Showtime.starts_at.between(start_dt, end_dt))

        stmt = stmt.distinct()

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await self._session.execute(count_stmt)).scalar() or 0

        offset = (page - 1) * limit
        stmt = stmt.order_by(Movie.created_at.desc()).offset(offset).limit(limit)

        result = await self._session.execute(stmt)
        movies = result.scalars().all()

        dtos = [
            MovieSummaryDTO(
                id=m.id,
                title=m.title,
                genre=m.genre,
                original_title=m.original_title,
                language=m.language,
                duration_min=m.duration_min,
                certificate=m.certificate,
                release_date=m.release_date,
                poster_url=m.poster_url,
                banner_url=m.banner_url,
                trailer_url=m.trailer_url,  
                status=m.status,
            )
            for m in movies
        ]
        return dtos, total

    async def get_movie_details(self, movie_id: UUID) -> MovieDetailsDTO | None:
        stmt = select(Movie).where(
            Movie.id == movie_id,
            Movie.status == MovieStatus.PUBLISHED.value,
        )
        res = await self._session.execute(stmt)
        movie = res.scalar_one_or_none()
        if not movie:
            return None

        st_stmt = (
            select(Showtime, Screen, Venue)
            .join(Screen, Showtime.screen_id == Screen.id)
            .join(Venue, Screen.venue_id == Venue.id)
            .where(
                Showtime.movie_id == movie_id,
                Showtime.status == ShowtimeStatus.ACTIVE.value,
            )
            .order_by(Venue.name.asc(), Showtime.starts_at.asc())
        )
        st_res = await self._session.execute(st_stmt)
        rows = st_res.all()

        venues_map: dict[UUID, VenueShowtimesDTO] = {}
        for st, screen, venue in rows:
            if venue.id not in venues_map:
                venues_map[venue.id] = VenueShowtimesDTO(
                    venue_id=venue.id,
                    venue_name=venue.name,
                    city=venue.city,
                    address=venue.address,
                    showtimes=[],
                )

            venues_map[venue.id].showtimes.append(
                ShowtimeSlotDTO(
                    id=st.id,
                    screen_id=screen.id,
                    screen_name=screen.name,
                    starts_at=st.starts_at,
                    language=st.language,
                    format=st.format,
                    status=st.status,
                )
            )

        return MovieDetailsDTO(
            id=movie.id,
            title=movie.title,
            genre=movie.genre,
            original_title=movie.original_title,
            language=movie.language,
            duration_min=movie.duration_min,
            certificate=movie.certificate,
            release_date=movie.release_date,
            poster_url=movie.poster_url,
            banner_url=movie.banner_url,
            trailer_url=movie.trailer_url,
            synopsis=movie.synopsis,
            status=movie.status,
            venues=list(venues_map.values()),
        )

    async def get_seat_map(self, showtime_id: UUID) -> SeatMapDTO | None:
        st_stmt = (
            select(Showtime, Movie, Screen, Venue)
            .join(Movie, Showtime.movie_id == Movie.id)
            .join(Screen, Showtime.screen_id == Screen.id)
            .join(Venue, Screen.venue_id == Venue.id)
            .where(Showtime.id == showtime_id)
        )
        st_res = await self._session.execute(st_stmt)
        st_row = st_res.first()
        if not st_row:
            return None

        showtime, movie, screen, venue = st_row

        rows_stmt = (
            select(ScreenRow)
            .where(ScreenRow.screen_id == screen.id)
            .order_by(ScreenRow.label.asc())
        )
        rows_res = await self._session.execute(rows_stmt)
        screen_rows = rows_res.scalars().all()

        row_ids = [r.id for r in screen_rows]

        seats_stmt = (
            select(Seat)
            .where(Seat.row_id.in_(row_ids))
            .order_by(Seat.x.asc(), Seat.number.asc())
        )
        seats_res = await self._session.execute(seats_stmt)
        all_seats = seats_res.scalars().all()

        seats_by_row: dict[UUID, list[Seat]] = {r.id: [] for r in screen_rows}
        for s in all_seats:
            if s.row_id in seats_by_row:
                seats_by_row[s.row_id].append(s)

        states_stmt = select(SeatState).where(SeatState.showtime_id == showtime_id)
        states_res = await self._session.execute(states_stmt)
        seat_states_map = {ss.seat_id: ss.status for ss in states_res.scalars().all()}

        row_dtos: list[RowProjectionDTO] = []
        for r in screen_rows:
            seat_dtos: list[SeatProjectionDTO] = []
            for s in seats_by_row.get(r.id, []):
                state_status = seat_states_map.get(s.id)
                if state_status == "BOOKED":
                    status = SeatStatus.BOOKED
                elif state_status == "BLOCKED":
                    status = SeatStatus.BLOCKED
                else:
                    status = SeatStatus.AVAILABLE

                seat_dtos.append(
                    SeatProjectionDTO(
                        seat_id=s.id,
                        number=s.number,
                        code=s.code,
                        x=s.x,
                        label=s.label,
                        status=status,
                        price_paise=r.price_paise,
                    )
                )

            row_dtos.append(
                RowProjectionDTO(
                    row_id=r.id,
                    label=r.label,
                    section=r.section,
                    price_paise=r.price_paise,
                    seats=seat_dtos,
                )
            )

        return SeatMapDTO(
            showtime_id=showtime.id,
            movie_id=movie.id,
            movie_title=movie.title,
            venue_name=venue.name,
            screen_name=screen.name,
            starts_at=showtime.starts_at,
            format=showtime.format,
            language=showtime.language,
            rows=row_dtos,
        )

    async def get_showtime_availability(
        self, showtime_id: UUID
    ) -> ShowtimeAvailabilityDTO | None:
        st_stmt = (
            select(Showtime, Screen)
            .join(Screen, Showtime.screen_id == Screen.id)
            .where(Showtime.id == showtime_id)
        )
        st_res = await self._session.execute(st_stmt)
        st_row = st_res.first()
        if not st_row:
            return None

        showtime, screen = st_row
        total_seats = screen.total_seats

        now = utcnow()
        states_stmt = select(SeatState).where(SeatState.showtime_id == showtime_id)
        states_res = await self._session.execute(states_stmt)
        states = states_res.scalars().all()

        booked = 0
        locked = 0
        blocked = 0
        for s in states:
            if s.status == "BOOKED":
                booked += 1
            elif s.status == "BLOCKED":
                blocked += 1
            elif s.status == "LOCKED":
                # Compute expiry at read time dynamically
                if s.held_until and s.held_until > now:
                    locked += 1

        available = max(0, total_seats - booked - locked - blocked)

        return ShowtimeAvailabilityDTO(
            showtime_id=showtime_id,
            total_seats=total_seats,
            available_seats=available,
            booked_seats=booked,
            blocked_seats=blocked,
            locked_seats=locked,
        )

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
        banner_url: str | None = None,      
        synopsis: str | None = None,
    ) -> MovieSummaryDTO:
        movie = Movie(
            id=uuid.uuid4(),
            title=title,
            original_title=original_title,
            language=language,
            duration_min=duration_min,
            certificate=certificate,
            status=MovieStatus.DRAFT.value,
            partner_id=partner_id,
            poster_url=poster_url,
            banner_url=banner_url,
            synopsis=synopsis,
        )
        self._session.add(movie)
        await self._session.commit()

        return MovieSummaryDTO(
            id=movie.id,
            title=movie.title,
            original_title=movie.original_title,
            language=movie.language,
            duration_min=movie.duration_min,
            certificate=movie.certificate,
            release_date=movie.release_date,
            poster_url=movie.poster_url,
            banner_url=movie.banner_url,
            genre=movie.genre,
            status=movie.status,
        )

    async def update_movie(
        self, movie_id: UUID, partner_id: UUID, updates: dict
    ) -> MovieSummaryDTO:
        stmt = select(Movie).where(Movie.id == movie_id)
        res = await self._session.execute(stmt)
        movie = res.scalar_one_or_none()
        if not movie:
            raise MovieNotFoundError(f"Movie '{movie_id}' not found")

        if movie.partner_id != partner_id:
            raise PartnerOwnershipError("Not authorized to modify this movie")

        for key, val in updates.items():
            if val is not None and hasattr(movie, key):
                setattr(movie, key, val)

        await self._session.commit()

        return MovieSummaryDTO(
            id=movie.id,
            title=movie.title,
            original_title=movie.original_title,
            language=movie.language,
            duration_min=movie.duration_min,
            certificate=movie.certificate,
            release_date=movie.release_date,
            poster_url=movie.poster_url,
            banner_url=movie.banner_url,
            genre=movie.genre,
            status=movie.status,
        )

    async def update_movie_status(
        self, movie_id: UUID, new_status: str
    ) -> MovieSummaryDTO:
        stmt = select(Movie).where(Movie.id == movie_id)
        res = await self._session.execute(stmt)
        movie = res.scalar_one_or_none()
        if not movie:
            raise MovieNotFoundError(f"Movie '{movie_id}' not found")

        movie.status = new_status
        await self._session.commit()

        return MovieSummaryDTO(
            id=movie.id,
            title=movie.title,
            original_title=movie.original_title,
            language=movie.language,
            duration_min=movie.duration_min,
            genre=movie.genre,
            certificate=movie.certificate,
            release_date=movie.release_date,
            poster_url=movie.poster_url,
            banner_url=movie.banner_url,
            status=movie.status,
        )

    async def create_screen(
        self, venue_id: UUID, name: str, partner_id: UUID
    ) -> UUID:
        v_stmt = select(Venue).where(Venue.id == venue_id)
        v_res = await self._session.execute(v_stmt)
        venue = v_res.scalar_one_or_none()
        if not venue:
            raise VenueNotFoundError(f"Venue '{venue_id}' not found")

        if venue.partner_id and venue.partner_id != partner_id:
            raise PartnerOwnershipError("Not authorized to add screen to this venue")

        screen = Screen(
            id=uuid.uuid4(),
            venue_id=venue_id,
            name=name,
            total_seats=0,
        )
        self._session.add(screen)
        await self._session.commit()
        return screen.id

    async def apply_screen_layout(
        self, screen_id: UUID, parsed_rows: list, is_admin_override: bool = False
    ) -> int:
        scr_stmt = select(Screen).where(Screen.id == screen_id)
        scr_res = await self._session.execute(scr_stmt)
        screen = scr_res.scalar_one_or_none()
        if not screen:
            raise ScreenNotFoundError(f"Screen '{screen_id}' not found")

        # Guard M12: Check if any active seat_states exist for showtimes on this screen
        states_check_stmt = (
            select(func.count())
            .select_from(SeatState)
            .join(Showtime, SeatState.showtime_id == Showtime.id)
            .where(Showtime.screen_id == screen_id)
        )
        active_states_count = (await self._session.execute(states_check_stmt)).scalar() or 0

        if active_states_count > 0 and not is_admin_override:
            raise ScreenLayoutLockedError(
                "M12 Violation: Cannot regenerate screen layout while active seat_states exist."
            )

        # Clear existing seats & rows safely
        row_ids_stmt = select(ScreenRow.id).where(ScreenRow.screen_id == screen_id)
        existing_row_ids = (await self._session.execute(row_ids_stmt)).scalars().all()

        if existing_row_ids:
            await self._session.execute(
                delete(Seat).where(Seat.row_id.in_(existing_row_ids))
            )
            await self._session.execute(
                delete(ScreenRow).where(ScreenRow.screen_id == screen_id)
            )

        # Generate new Rows & Seats
        total_created = 0
        for pr in parsed_rows:
            sr = ScreenRow(
                id=uuid.uuid4(),
                screen_id=screen_id,
                label=pr.label,
                section=pr.section,
                seat_count=pr.seat_count,
                price_paise=pr.price_paise,
            )
            self._session.add(sr)
            await self._session.flush()

            for ps in pr.seats:
                self._session.add(
                    Seat(
                        id=uuid.uuid4(),
                        row_id=sr.id,
                        number=ps.number,
                        code=ps.code,
                        x=ps.x,
                        label=ps.label,
                    )
                )
            total_created += pr.seat_count

        screen.total_seats = total_created
        await self._session.commit()
        return total_created

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
        m_stmt = select(Movie).where(Movie.id == movie_id)
        movie = (await self._session.execute(m_stmt)).scalar_one_or_none()
        if not movie:
            raise MovieNotFoundError(f"Movie '{movie_id}' not found")

        scr_stmt = select(Screen).where(Screen.id == screen_id)
        screen = (await self._session.execute(scr_stmt)).scalar_one_or_none()
        if not screen:
            raise ScreenNotFoundError(f"Screen '{screen_id}' not found")

        st = Showtime(
            id=uuid.uuid4(),
            screen_id=screen_id,
            movie_id=movie_id,
            starts_at=starts_at,
            language=language,
            format=format,
            status=ShowtimeStatus.ACTIVE.value,
            partner_id=partner_id,
        )
        self._session.add(st)
        await self._session.commit()
        return st.id

    async def cancel_showtime(
        self, showtime_id: UUID, partner_id: UUID
    ) -> bool:
        st_stmt = select(Showtime).where(Showtime.id == showtime_id)
        st = (await self._session.execute(st_stmt)).scalar_one_or_none()
        if not st:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")

        if st.partner_id != partner_id:
            raise PartnerOwnershipError("Not authorized to cancel this showtime")

        from datetime import timedelta
        if st.starts_at + timedelta(hours=2) < utcnow():
            from app.movie.interfaces import DomainError
            raise DomainError("Cannot cancel a showtime in the past")

        st.status = ShowtimeStatus.CANCELLED.value

        # Delete all seat_states for this showtime
        await self._session.execute(
            delete(SeatState).where(SeatState.showtime_id == showtime_id)
        )

        # Cancel all bookings for this showtime
        from app.booking.models import BookingModel
        await self._session.execute(
            update(BookingModel)
            .where(BookingModel.showtime_id == showtime_id, BookingModel.status == "CONFIRMED")
            .values(status="CANCELLED")
        )

        # Reset movie_sold_counts
        await self._session.execute(
            update(MovieSoldCount)
            .where(MovieSoldCount.showtime_id == showtime_id)
            .values(sold_count=0)
        )

        await self._session.commit()
        return True

    async def block_seats(
        self, showtime_id: UUID, seat_ids: list[UUID], reason: str
    ) -> bool:
        st_stmt = select(Showtime).where(Showtime.id == showtime_id)
        st = (await self._session.execute(st_stmt)).scalar_one_or_none()
        if not st:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")

        for s_id in seat_ids:
            seat_stmt = select(Seat).where(Seat.id == s_id)
            seat = (await self._session.execute(seat_stmt)).scalar_one_or_none()
            if not seat:
                raise SeatNotFoundError(f"Seat '{s_id}' not found")

            ss = SeatState(
                showtime_id=showtime_id,
                seat_id=s_id,
                status=SeatStateStatus.BLOCKED.value,
                blocked_reason=reason,
            )
            self._session.add(ss)

        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise SeatAlreadyBookedError(
                "One or more seats are already booked or blocked"
            ) from exc

        return True
    
    async def unblock_seats(
        self, showtime_id: UUID, seat_ids: list[UUID]
    ) -> bool:
        st_stmt = select(Showtime).where(Showtime.id == showtime_id)
        st = (await self._session.execute(st_stmt)).scalar_one_or_none()
        if not st:
            raise ShowtimeNotFoundError(f"Showtime '{showtime_id}' not found")

        stmt = delete(SeatState).where(
            SeatState.showtime_id == showtime_id,
            SeatState.seat_id.in_(seat_ids),
            SeatState.status == SeatStateStatus.BLOCKED.value,
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return True