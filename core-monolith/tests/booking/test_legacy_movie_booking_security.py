import pytest
import uuid
from datetime import datetime, timezone, timedelta
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.database import get_db
from app.auth.models import User
from app.auth.interfaces import UserRole
from app.movie.models import Venue, Movie, MovieStatus, Screen, ScreenRow, Seat, Showtime, ShowtimeStatus
from app.payment.models import PaymentModel
from app.auth.security import JWTTokenService


def _token_for(user_id: uuid.UUID) -> str:
    from app.auth.interfaces import User as UserDomain
    u = UserDomain(
        id=user_id,
        email="test@local",
        full_name="Tester",
        password_hash="dummy_hash",
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
    )
    return JWTTokenService().create_access_token(u)


async def _seed_movie_showtime(session: AsyncSession, seat_price_paise: int = 25000):
    user = User(
        id=uuid.uuid4(),
        full_name="Movie Fan",
        email=f"fan_{uuid.uuid4().hex[:6]}@test.local",
        password_hash="h",
        role="USER",
        is_active=True,
    )
    movie = Movie(
        id=uuid.uuid4(),
        title="Security Audit Movie",
        synopsis="A movie",
        duration_min=120,
        language="English",
        certificate="U",
        partner_id=uuid.uuid4(),
        status=MovieStatus.PUBLISHED.value,
    )
    venue = Venue(id=uuid.uuid4(), name="Venue 1", city="Bengaluru")
    screen = Screen(id=uuid.uuid4(), name="Screen 1", total_seats=10, venue_id=venue.id)
    row = ScreenRow(
        id=uuid.uuid4(),
        screen_id=screen.id,
        label="A",
        seat_count=10,
        price_paise=seat_price_paise,
    )
    seat = Seat(
        id=uuid.uuid4(),
        row_id=row.id,
        number=1,
        code="A1",
        x=0,
        label="A1",
    )
    showtime = Showtime(
        id=uuid.uuid4(),
        movie_id=movie.id,
        screen_id=screen.id,
        partner_id=movie.partner_id,
        starts_at=datetime.now(timezone.utc) + timedelta(days=1),
        status=ShowtimeStatus.ACTIVE.value,
        provider_id=None,
    )
    session.add_all([user, venue, movie, screen, row, seat, showtime])
    await session.commit()
    return {"user": user, "venue": venue, "movie": movie, "screen": screen, "row": row, "seat": seat, "showtime": showtime}


@pytest.mark.asyncio
async def test_legacy_movie_booking_requires_captured_payment_when_total_positive(session: AsyncSession):
    """Calling POST /bookings with showtime and seats but empty payment MUST fail with 402."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_movie_showtime(session, seat_price_paise=30000)
    token = _token_for(data["user"].id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Empty payment_id
        resp = await client.post(
            "/v1/bookings",
            json={
                "showtime_id": str(data["showtime"].id),
                "seat_ids": [str(data["seat"].id)],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 402, f"Expected 402, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["error"]["type"] == "PAYMENT_VERIFICATION_FAILED"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_legacy_movie_booking_rejects_uncaptured_payment(session: AsyncSession):
    """Calling POST /bookings with a non-captured payment MUST fail with 402."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_movie_showtime(session, seat_price_paise=30000)
    token = _token_for(data["user"].id)

    from app.booking.models import BookingModel
    dummy_booking = BookingModel(
        id=uuid.uuid4(),
        user_id=data["user"].id,
        booking_type="MOVIE",
        showtime_id=data["showtime"].id,
        ref_code="BKDUMMY1",
        total_paise=30000,
        status="HELD",
    )
    session.add(dummy_booking)
    await session.flush()

    dummy_payment = PaymentModel(
        id=uuid.uuid4(),
        booking_id=dummy_booking.id,
        order_id="order_pending_123",
        payment_id="pay_pending_123",
        amount_paise=30000,
        currency="INR",
        status="PENDING",
    )
    session.add(dummy_payment)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings",
            json={
                "showtime_id": str(data["showtime"].id),
                "seat_ids": [str(data["seat"].id)],
                "payment_id": "pay_pending_123",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 402
        assert resp.json()["error"]["type"] == "PAYMENT_VERIFICATION_FAILED"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_legacy_movie_booking_succeeds_with_captured_payment(session: AsyncSession):
    """Calling POST /bookings with a valid captured payment succeeds."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_movie_showtime(session, seat_price_paise=30000)
    token = _token_for(data["user"].id)

    from app.booking.models import BookingModel
    dummy_booking = BookingModel(
        id=uuid.uuid4(),
        user_id=data["user"].id,
        booking_type="MOVIE",
        showtime_id=data["showtime"].id,
        ref_code="BKDUMMY2",
        total_paise=30000,
        status="HELD",
    )
    session.add(dummy_booking)
    await session.flush()

    captured_payment = PaymentModel(
        id=uuid.uuid4(),
        booking_id=dummy_booking.id,
        order_id="order_captured_123",
        payment_id="pay_captured_123",
        amount_paise=30000,
        currency="INR",
        status="CAPTURED",
        signature_verified=True,
    )
    session.add(captured_payment)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings",
            json={
                "showtime_id": str(data["showtime"].id),
                "seat_ids": [str(data["seat"].id)],
                "payment_id": "pay_captured_123",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["booking"]["status"] == "CONFIRMED"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_legacy_movie_booking_succeeds_for_zero_total_without_payment(session: AsyncSession):
    """Free movie seats (0 paise) succeed without payment."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_movie_showtime(session, seat_price_paise=0)
    token = _token_for(data["user"].id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings",
            json={
                "showtime_id": str(data["showtime"].id),
                "seat_ids": [str(data["seat"].id)],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201
        assert resp.json()["booking"]["status"] == "CONFIRMED"

    app.dependency_overrides.clear()
