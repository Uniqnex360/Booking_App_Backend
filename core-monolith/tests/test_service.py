import pytest
import pytest_asyncio
import asyncio
import uuid
from sqlalchemy import text
from datetime import timedelta, datetime
from app.shared.timeutil import utcnow

# --- 1. Imports ---
from app.partner.models import PartnerORM
from app.auth.models import User
from app.event.models import EventORM as Event, TicketCategoryORM as EventTicketCategory
from app.booking.models import BookingModel, TicketSoldCountModel

from app.booking.repository import BookingRepository, TierCounterRepository
from app.booking.services import BookingService
from app.booking.interfaces import (
    SoldOutError, QuantityExceedsMaxError,
    EventNotBookableError, BookingNotCancellableError, BookingNotFoundError
)

# --- 2. Database Helpers (Strict Schema Alignment) ---

async def create_test_user(session, user_id, email, role, phone=None):
    """Satisfies User Table: Role must be UPPERCASE."""
    now = utcnow().replace(tzinfo=None)
    if phone is None:
        phone = str(user_id)[:10]
    await session.execute(
        text("""
            INSERT INTO users (
                id, full_name, phone, email, password_hash, role,
                is_verified, is_active, created_at, updated_at
            ) VALUES (
                :id, 'Test User', :phone, :email, 'hash', :role,
                True, True, :now, :now
            )
        """),
        {"id": user_id, "phone": phone, "email": email, "role": role, "now": now}
    )

async def create_test_partner(session, partner_id, p_user_id):
    now = datetime.utcnow()
    await session.execute(
        text("""
            INSERT INTO partners (
                id, user_id, business_name, partner_type,
                contact_name, contact_phone, city,
                commission_rate,
                status, created_at, updated_at
            ) VALUES (
                :pid, :puid, 'Test Business', 'ORGANIZATION',
                'Admin', '0000000000', 'Test City',
                10.0,
                'APPROVED', :now, :now
            )
        """),
        {"pid": partner_id, "puid": p_user_id, "now": now}
    )

# --- 3. Fixtures ---

@pytest_asyncio.fixture(scope="function")
async def booking_service(session):
    return BookingService(
        booking_repo=BookingRepository(session),
        counter_repo=TierCounterRepository(session)
    )

@pytest_asyncio.fixture(scope="function")
async def session_factory(engine):
    """Factory to create new isolated sessions for concurrent tasks."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async def make_session():
        async with factory() as sess:
            yield sess
    
    return make_session

@pytest_asyncio.fixture(scope="function")
async def setup_tier(session):
    async def _setup(capacity=100, max_per=10, status="PUBLISHED", price=5000):
        p_user_id = uuid.uuid4()
        await create_test_user(session, p_user_id, f"p-{p_user_id}@t.com", "PARTNER")
        partner_id = uuid.uuid4()
        await create_test_partner(session, partner_id, p_user_id)

        event_id = uuid.uuid4()
        session.add(Event(
            id=event_id, partner_id=partner_id, title="Test Event",
            slug=f"slug-{event_id}", category="Music", venue_name="V",
            city="Kochi", starts_at=utcnow(), ends_at=utcnow() + timedelta(hours=2),
            status=status, event_type="STANDARD", seating_mode="TIER"
        ))

        tier_id = uuid.uuid4()
        session.add(EventTicketCategory(
            id=tier_id, event_id=event_id, name="General",
            capacity=capacity, price_paise=price,
            max_per_booking=max_per, is_active=True
        ))
        await session.flush()
        return tier_id
    return _setup

# --- 4. Tests (B1-B15) ---

@pytest.mark.asyncio
async def test_b1_b2_basic_booking_and_sold_out(booking_service, session, setup_tier):
    tier_id = await setup_tier(capacity=10)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, f"{user_id}@t.com", "USER")
    await session.flush()

    booking = await booking_service.create_booking(user_id, tier_id, quantity=2)
    assert booking.total_paise == 10000

    res = await session.execute(text("SELECT sold FROM ticket_sold_counts WHERE tier_id=:t"), {"t": tier_id})
    assert res.scalar() == 2

    with pytest.raises(SoldOutError):
        await booking_service.create_booking(user_id, tier_id, quantity=9)
@pytest.mark.asyncio
async def test_b3_race_condition_concurrency(engine, session, setup_tier):
    """20 concurrent requests, each with isolated session, capacity=100, 8 each = 12 succeed."""
    tier_id = await setup_tier(capacity=100, max_per=10)
    uids = [uuid.uuid4() for _ in range(20)]
    for uid in uids:
        await create_test_user(session, uid, f"{uid}@t.com", "USER")
    await session.commit()  # Commit users so concurrent sessions can see them

    async def make_booking(user_id):
        # Each task gets its own session
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as sess:
            service = BookingService(
                booking_repo=BookingRepository(sess),
                counter_repo=TierCounterRepository(sess)
            )
            result = await service.create_booking(user_id, tier_id, 8)
            await sess.commit()
            return result

    tasks = [make_booking(uids[i]) for i in range(20)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    assert len(successes) == 12  # 100 / 8 = 12.5, so 12 succeed
    
    # Verify the counter was updated correctly
    res = await session.execute(text("SELECT sold FROM ticket_sold_counts WHERE tier_id=:t"), {"t": tier_id})
    assert res.scalar() == 96

    # NEW: Verify that exactly 12 booking rows were actually written to the DB
    from sqlalchemy import select, func
    from app.booking.models import BookingModel
    
    booking_count = (await session.execute(
        select(func.count()).select_from(BookingModel).where(BookingModel.tier_id == tier_id)
    )).scalar_one()
    
    assert booking_count == 12, f"Expected exactly 12 booking rows in DB, found {booking_count}"
@pytest.mark.asyncio
async def test_b8b_idempotency_does_not_burn_capacity(booking_service, session, setup_tier):
    tier_id = await setup_tier(capacity=10)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b8b@t.com", "USER")
    await session.flush()

    ikey = "fixed-key"
    await booking_service.create_booking(user_id, tier_id, 2, idempotency_key=ikey)
    await booking_service.create_booking(user_id, tier_id, 2, idempotency_key=ikey)

    res = await session.execute(text("SELECT sold FROM ticket_sold_counts WHERE tier_id=:t"), {"t": tier_id})
    assert res.scalar() == 2

@pytest.mark.asyncio
async def test_b9_b10_cancel_lifecycle(booking_service, session, setup_tier):
    tier_id = await setup_tier(capacity=10)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b9@t.com", "USER")
    await session.flush()

    booking = await booking_service.create_booking(user_id, tier_id, 5)
    await booking_service.cancel_booking(booking.id, user_id=user_id)

    res = await session.execute(text("SELECT sold FROM ticket_sold_counts WHERE tier_id=:t"), {"t": tier_id})
    assert res.scalar() == 0

    with pytest.raises(BookingNotCancellableError):
        await booking_service.cancel_booking(booking.id, user_id=user_id)

@pytest.mark.asyncio
async def test_b13_capacity_edit_affects_next_booking(booking_service, session, setup_tier):
    tier_id = await setup_tier(capacity=100)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b13@t.com", "USER")
    user_id_2 = uuid.uuid4()
    await create_test_user(session, user_id_2, "b13b@t.com", "USER")
    await session.flush()

    await booking_service.create_booking(user_id, tier_id, 4)
    await session.execute(text("UPDATE event_ticket_categories SET capacity = 5 WHERE id = :t"), {"t": tier_id})

    with pytest.raises(SoldOutError):
        await booking_service.create_booking(user_id_2, tier_id, 2)

def test_b15_static_boundary_check():
    import pathlib
    content = pathlib.Path("app/booking/services.py").read_text()
    assert "from fastapi" not in content
    assert "app.event" not in content


# --- 5. Additional Tests (B2, B4-B8, B11, B12, B14, B16, B17) ---

@pytest.mark.asyncio
async def test_b2_sold_out_after_exact_fill(booking_service, session, setup_tier):
    """Filling capacity exactly, then one more raises SoldOutError."""
    tier_id = await setup_tier(capacity=5, max_per=5)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b2@t.com", "USER")
    await session.flush()

    await booking_service.create_booking(user_id, tier_id, quantity=5)

    user_id_2 = uuid.uuid4()
    await create_test_user(session, user_id_2, "b2b@t.com", "USER")
    await session.flush()

    with pytest.raises(SoldOutError):
        await booking_service.create_booking(user_id_2, tier_id, quantity=1)


@pytest.mark.asyncio
async def test_b4_max_per_booking_enforcement(booking_service, session, setup_tier):
    """Quantity exceeding max_per_booking raises QuantityExceedsMaxError."""
    tier_id = await setup_tier(capacity=100, max_per=5)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b4@t.com", "USER")
    await session.flush()

    with pytest.raises(QuantityExceedsMaxError):
        await booking_service.create_booking(user_id, tier_id, quantity=6)

    booking = await booking_service.create_booking(user_id, tier_id, quantity=5)
    assert booking.quantity == 5


@pytest.mark.asyncio
async def test_b5_event_not_bookable(booking_service, session, setup_tier):
    """Booking against a DRAFT event raises EventNotBookableError."""
    tier_id = await setup_tier(capacity=10, status="DRAFT")
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b5@t.com", "USER")
    await session.flush()

    with pytest.raises(EventNotBookableError):
        await booking_service.create_booking(user_id, tier_id, quantity=1)


@pytest.mark.asyncio
async def test_b6_inactive_tier_rejected(booking_service, session, setup_tier):
    """Booking against an inactive tier raises EventNotBookableError."""
    tier_id = await setup_tier(capacity=10)
    await session.execute(
        text("UPDATE event_ticket_categories SET is_active = false WHERE id = :t"),
        {"t": tier_id}
    )
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b6@t.com", "USER")
    await session.flush()

    # Service raises TierInactiveError for inactive tiers
    from app.booking.interfaces import TierInactiveError
    with pytest.raises(TierInactiveError):
        await booking_service.create_booking(user_id, tier_id, quantity=1)

@pytest.mark.asyncio
async def test_b7_zero_quantity_rejected(booking_service, session, setup_tier):
    """Zero or negative quantity raises an error."""
    tier_id = await setup_tier(capacity=10)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b7@t.com", "USER")
    await session.flush()

    from sqlalchemy import select
    from app.booking.models import TicketSoldCountModel

    # Check initial sold count (might be None if row doesn't exist yet, or 0)
    initial_sold = (await session.execute(
        select(TicketSoldCountModel.sold).where(TicketSoldCountModel.tier_id == tier_id)
    )).scalar_one_or_none()
    assert initial_sold in (0, None), f"Initial sold should be 0 or None, got {initial_sold}"

    # quantity=0 should be rejected
    with pytest.raises(ValueError, match="Quantity must be greater than 0"):
        await booking_service.create_booking(user_id, tier_id, quantity=0)

    # quantity=-3 should be rejected
    with pytest.raises(ValueError, match="Quantity must be greater than 0"):
        await booking_service.create_booking(user_id, tier_id, quantity=-3)

    # Assert that sold did NOT move
    final_sold = (await session.execute(
        select(TicketSoldCountModel.sold).where(TicketSoldCountModel.tier_id == tier_id)
    )).scalar_one_or_none()
    assert final_sold in (0, None), f"Final sold should still be 0 or None, got {final_sold}"

@pytest.mark.asyncio
async def test_b8_exact_capacity_fill(booking_service, session, setup_tier):
    """Booking that exactly fills capacity succeeds; next fails with SoldOutError."""
    tier_id = await setup_tier(capacity=10, max_per=10)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b8@t.com", "USER")
    await session.flush()

    booking = await booking_service.create_booking(user_id, tier_id, quantity=10)
    assert booking.quantity == 10

    res = await session.execute(text("SELECT sold FROM ticket_sold_counts WHERE tier_id=:t"), {"t": tier_id})
    assert res.scalar() == 10

    user_id_2 = uuid.uuid4()
    await create_test_user(session, user_id_2, "b8b@t.com", "USER")
    await session.flush()

    with pytest.raises(SoldOutError):
        await booking_service.create_booking(user_id_2, tier_id, quantity=1)


@pytest.mark.asyncio
async def test_b11_cancel_restores_capacity(booking_service, session, setup_tier):
    """After cancel, a new booking can use the freed capacity."""
    tier_id = await setup_tier(capacity=5)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b11@t.com", "USER")
    await session.flush()

    booking = await booking_service.create_booking(user_id, tier_id, 5)
    await booking_service.cancel_booking(booking.id, user_id=user_id)

    user_id_2 = uuid.uuid4()
    await create_test_user(session, user_id_2, "b11b@t.com", "USER")
    await session.flush()

    booking2 = await booking_service.create_booking(user_id_2, tier_id, 3)
    assert booking2.quantity == 3


@pytest.mark.asyncio
async def test_b12_cancel_by_non_owner_fails(booking_service, session, setup_tier):
    """Cancelling another user booking raises BookingNotCancellableError."""
    tier_id = await setup_tier(capacity=10)
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    await create_test_user(session, user_a, "b12a@t.com", "USER")
    await create_test_user(session, user_b, "b12b@t.com", "USER")
    await session.flush()

    booking = await booking_service.create_booking(user_a, tier_id, 2)

    # Ownership check now raises BookingNotFoundError (not BookingNotCancellableError)
    # to avoid leaking whether a booking exists to a non-owner.
    with pytest.raises(BookingNotFoundError):
        await booking_service.cancel_booking(booking.id, user_id=user_b)


@pytest.mark.asyncio
async def test_b14_booking_status_transitions(booking_service, session, setup_tier):
    """After creation status is CONFIRMED; after cancel it is CANCELLED."""
    tier_id = await setup_tier(capacity=10)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b14@t.com", "USER")
    await session.flush()

    booking = await booking_service.create_booking(user_id, tier_id, 1)
    assert booking.status == "CONFIRMED"

    await booking_service.cancel_booking(booking.id, user_id=user_id)

    res = await session.execute(
        text("SELECT status FROM bookings WHERE id = :id"),
        {"id": booking.id}
    )
    assert res.scalar() == "CANCELLED"


@pytest.mark.asyncio
async def test_b16_same_user_different_idempotency_key(booking_service, session, setup_tier):
    """Same user, different idempotency key = two separate bookings."""
    tier_id = await setup_tier(capacity=10)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b16@t.com", "USER")
    await session.flush()

    b1 = await booking_service.create_booking(user_id, tier_id, 2, idempotency_key="key-A")
    b2 = await booking_service.create_booking(user_id, tier_id, 3, idempotency_key="key-B")

    assert b1.id != b2.id
    assert b1.quantity == 2
    assert b2.quantity == 3

    res = await session.execute(text("SELECT sold FROM ticket_sold_counts WHERE tier_id=:t"), {"t": tier_id})
    assert res.scalar() == 5

@pytest.mark.asyncio
async def test_b17_concurrent_same_key_yields_one_booking(engine, session, setup_tier):
    """20 concurrent requests with same idempotency key produce exactly one booking."""
    tier_id = await setup_tier(capacity=100)
    user_id = uuid.uuid4()
    await create_test_user(session, user_id, "b17@t.com", "USER")
    await session.commit()

    async def make_booking():
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as sess:
            service = BookingService(
                booking_repo=BookingRepository(sess),
                counter_repo=TierCounterRepository(sess)
            )
            result = await service.create_booking(user_id, tier_id, 2, idempotency_key="concurrent-key")
            await sess.commit()
            return result

    tasks = [make_booking() for _ in range(20)]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    # All successes must refer to the SAME booking (idempotency)
    assert len(successes) >= 1, f"Expected at least one success, got {len(successes)}; failures={failures}"
    assert len({r.id for r in successes}) == 1, (
        f"All successes should share one booking id, got {[r.id for r in successes]}"
    )

    # Exactly ONE row in the DB
    from sqlalchemy import select, func
    from app.booking.models import BookingModel  # adjust import
    count = (await session.execute(
        select(func.count()).select_from(BookingModel)
        .where(BookingModel.idempotency_key == "concurrent-key")
    )).scalar_one()
    assert count == 1, f"Expected 1 booking row, found {count}"

    # Counter consumed exactly once
    from app.booking.models import TicketSoldCountModel  # adjust
    consumed = (await session.execute(
        select(TicketSoldCountModel.sold).where(TicketSoldCountModel.tier_id == tier_id)
    )).scalar_one()
    assert consumed == 2, f"Expected sold_count=2, got {consumed}"