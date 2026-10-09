import pytest
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.booking.interfaces import SoldOutError, ValidationError
from app.booking.models import BookingModel
from app.booking.repository import BookingRepository, TierCounterRepository
from app.booking.services import BookingService
from app.event.models import EventORM, TicketCategoryORM
from app.movie.models import Venue, Screen, ScreenRow, Seat, Movie, Showtime, SeatState
from app.partner.models import PartnerORM
from app.auth.models import User


@pytest.mark.asyncio
async def test_50_parallel_holds_event_capacity(session: AsyncSession, engine):
    """SUS-01 verification: 50 concurrent hold requests for the LAST 1 remaining seat/capacity."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    partner_owner = User(
        id=uuid.uuid4(),
        full_name="Partner Owner",
        email=f"partner_{uuid.uuid4().hex[:6]}@example.com",
    )
    partner_id = uuid.uuid4()
    partner = PartnerORM(
        id=partner_id,
        user_id=partner_owner.id,
        business_name="Arena Partner",
        partner_type="EVENT_ORGANIZER",
        contact_name="Owner",
        contact_phone="9999999999",
        city="Bengaluru",
    )
    event_id = uuid.uuid4()
    tier_id = uuid.uuid4()

    event = EventORM(
        id=event_id,
        partner_id=partner_id,
        title="Exclusive Concurrency Concert",
        slug=f"exclusive-concert-{uuid.uuid4().hex[:6]}",
        venue_name="Main Arena",
        city="Bengaluru",
        venue_address="Arena Road",
        category="music",
        status="PUBLISHED",
        starts_at=datetime.now(timezone.utc) + timedelta(days=1),
        ends_at=datetime.now(timezone.utc) + timedelta(days=2),
    )
    tier = TicketCategoryORM(
        id=tier_id,
        event_id=event_id,
        name="VIP Final Seat",
        price_paise=100000,
        capacity=1,  # Only 1 capacity available!
        max_per_booking=1,
        is_active=True,
    )

    session.add_all([partner_owner, partner])
    await session.flush()
    session.add_all([event, tier])
    await session.commit()

    counter_repo = TierCounterRepository(session)
    await counter_repo.ensure_counter_row(tier_id)
    await session.commit()

    async def attempt_hold(user_num: int):
        user_id = uuid.uuid4()
        async with factory() as req_session:
            b_repo = BookingRepository(req_session)
            c_repo = TierCounterRepository(req_session)
            service = BookingService(
                booking_repo=b_repo,
                counter_repo=c_repo,
                session=req_session,
            )
            try:
                booking = await service.create_booking(
                    user_id=user_id,
                    tier_id=tier_id,
                    quantity=1,
                    idempotency_key=f"event-hold-{user_num}",
                )
                return ("SUCCESS", booking.id)
            except (SoldOutError, ValidationError):
                return ("SOLD_OUT", None)
            except Exception as e:
                return ("ERROR", f"{type(e).__name__}: {str(e)}")

    # Launch exactly 50 parallel hold attempts concurrently
    tasks = [attempt_hold(i) for i in range(50)]
    results = await asyncio.gather(*tasks)

    successes = [r for r in results if r[0] == "SUCCESS"]
    sold_outs = [r for r in results if r[0] == "SOLD_OUT"]
    errors = [r for r in results if r[0] == "ERROR"]

    assert len(errors) == 0, f"Unexpected errors: {errors}"
    # Exactly ONE hold must succeed
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}"
    # Exactly 49 attempts must be rejected as SOLD_OUT
    assert len(sold_outs) == 49, f"Expected exactly 49 sold outs, got {len(sold_outs)}"

    # Database verification: total bookings created for this tier must be 1
    total_bookings = (
        await session.execute(
            select(func.count(BookingModel.id)).where(BookingModel.tier_id == tier_id)
        )
    ).scalar()
    assert total_bookings == 1, f"Double-booking detected in DB! Total bookings: {total_bookings}"


@pytest.mark.asyncio
async def test_50_parallel_holds_cinema_seat(session: AsyncSession, engine):
    """SUS-01 verification: 50 concurrent hold requests for the EXACT SAME cinema seat."""
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    cinema_owner = User(
        id=uuid.uuid4(),
        full_name="Cinema Owner",
        email=f"cinema_{uuid.uuid4().hex[:6]}@example.com",
    )
    partner_id = uuid.uuid4()
    partner = PartnerORM(
        id=partner_id,
        user_id=cinema_owner.id,
        business_name="Cinema Partner",
        partner_type="CINEMA_OPERATOR",
        contact_name="Cinema Owner",
        contact_phone="9888888888",
        city="Bengaluru",
    )
    venue = Venue(id=uuid.uuid4(), name="PVR Concurrency", city="Bengaluru", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="IMAX 1")
    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=1, price_paise=25000)
    seat = Seat(id=uuid.uuid4(), row_id=row.id, number=1, code="A01", x=0)
    movie = Movie(
        id=uuid.uuid4(),
        title="Concurrency Blockbuster",
        language="English",
        duration_min=120,
        certificate="UA",
        status="PUBLISHED",
        partner_id=partner_id,
    )
    st = Showtime(
        id=uuid.uuid4(),
        screen_id=screen.id,
        movie_id=movie.id,
        starts_at=datetime.now(timezone.utc) + timedelta(hours=3),
        status="ACTIVE",
        partner_id=partner_id,
    )

    session.add_all([cinema_owner, partner])
    await session.flush()
    session.add_all([venue, screen, row, seat, movie, st])
    await session.commit()

    async def attempt_seat_hold(user_num: int):
        user_id = uuid.uuid4()
        async with factory() as req_session:
            b_repo = BookingRepository(req_session)
            c_repo = TierCounterRepository(req_session)
            service = BookingService(
                booking_repo=b_repo,
                counter_repo=c_repo,
                session=req_session,
            )
            try:
                booking = await service.create_seat_hold(
                    user_id=user_id,
                    showtime_id=st.id,
                    seat_ids=[seat.id],
                    idempotency_key=f"seat-hold-key-{user_num}",
                    seat_codes=["A01"],
                )
                return ("SUCCESS", booking.id)
            except ValidationError:
                # Seat unavailable / reservation conflict
                return ("REJECTED", None)
            except Exception as e:
                return ("ERROR", f"{type(e).__name__}: {str(e)}")

    # Launch 50 concurrent hold attempts for seat A01
    tasks = [attempt_seat_hold(i) for i in range(50)]
    results = await asyncio.gather(*tasks)

    successes = [r for r in results if r[0] == "SUCCESS"]
    rejected = [r for r in results if r[0] == "REJECTED"]
    errors = [r for r in results if r[0] == "ERROR"]

    assert len(errors) == 0, f"Unexpected errors: {errors}"
    # Exactly ONE hold succeeds for that seat
    assert len(successes) == 1, f"Expected 1 success, got {len(successes)}"
    assert len(rejected) == 49, f"Expected 49 rejections, got {len(rejected)}"

    # Database verification: exactly 1 LOCKED state in SeatState
    seat_states = (
        await session.execute(
            select(func.count(SeatState.seat_id)).where(
                SeatState.showtime_id == st.id,
                SeatState.seat_id == seat.id,
                SeatState.status.in_(["LOCKED", "BOOKED"]),
            )
        )
    ).scalar()
    assert seat_states == 1, f"Double-booking in SeatState detected! Count: {seat_states}"
