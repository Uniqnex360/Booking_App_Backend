"""
Missing Payment Tests Gap Suite.
Contains the 7 missing tests: H2b, H6, H8, H14, H17, H23, H24.
"""

import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
import sqlalchemy.exc

from app.auth.models import User
from app.booking.models import BookingModel
from app.booking.interfaces import ValidationError
from app.booking.services import BookingService
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.movie.models import Movie, Screen, ScreenRow, Seat, SeatState, Showtime, Venue
from app.partner.models import PartnerORM
from app.payment.models import PaymentModel, PaymentEventModel
from app.payment.interfaces import (
    BookingNotPayable,
    GatewayUnavailable,
    PaymentStatus,
    VerificationFailed,
)
from app.payment.services import PaymentService
from app.payment.repository import PaymentRepository
from app.payment.gateway import _get_key_secret, _get_key_id
from app.shared.timeutil import utcnow
from tests.payment.test_payment_module import _token_for, _seed_self_hosted_data


# ---------------------------------------------------------------------------
# H2b: Seat lock conflict surfaces as domain error (NOT a leaked IntegrityError)
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h2b_seat_lock_conflict_surfaces_as_domain_error(session: AsyncSession):
    data = await _seed_self_hosted_data(session)
    user2 = User(id=uuid.uuid4(), full_name="User 2", email="u2_gap@t.local", password_hash="pwd", role="USER", is_active=True)
    session.add(user2)
    await session.commit()

    target_seat = data["seats"][0].id
    showtime_id = data["showtime"].id

    # 1. Deterministically insert conflicting LOCKED row directly into seat_states
    existing_booking_id = uuid.uuid4()
    session.add(
        SeatState(
            showtime_id=showtime_id,
            seat_id=target_seat,
            status="LOCKED",
            booking_id=existing_booking_id,
            held_until=utcnow() + timedelta(minutes=10),
        )
    )
    await session.commit()

    # 2. Call service's hold function for that same seat and catch exception
    from app.booking.repository import BookingRepository, TierCounterRepository
    booking_service = BookingService(
        booking_repo=BookingRepository(session),
        counter_repo=TierCounterRepository(session),
        session=session,
    )

    with pytest.raises(Exception) as exc_info:
        await booking_service.create_seat_hold(
            user_id=user2.id,
            showtime_id=showtime_id,
            seat_ids=[target_seat],
            idempotency_key="h2b-key",
        )

    # 3. Assert it is the domain error and NOT a raw SQLAlchemy IntegrityError
    assert isinstance(exc_info.value, ValidationError)
    assert not isinstance(exc_info.value, sqlalchemy.exc.IntegrityError)


# ---------------------------------------------------------------------------
# H6: Cancel held booking with CREATED payment row -> frees seats, payment not confirmed
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h6_cancel_held_booking_with_created_payment(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD", held_until=utcnow() + timedelta(minutes=10))
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h6", amount_paise=25000, status="CREATED")
    ss = SeatState(showtime_id=data["showtime"].id, seat_id=data["seats"][0].id, status="LOCKED", booking_id=b.id, held_until=utcnow() + timedelta(minutes=10))
    session.add_all([p, ss])
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Cancel held booking
        del_resp = await client.delete(f"/v1/bookings/seat-hold/{b.id}", headers={"Authorization": f"Bearer {token}"})
        assert del_resp.status_code == 204

        # 2. Verify seats freed and booking cancelled
        b_refreshed = (await session.execute(select(BookingModel).where(BookingModel.id == b.id))).scalar_one()
        assert b_refreshed.status == "CANCELLED"
        seats_cnt = (await session.execute(select(func.count(SeatState.seat_id)).where(SeatState.booking_id == b.id))).scalar()
        assert seats_cnt == 0

        # 3. Delayed browser callback: verify arrives AFTER cancel -> returns 409 and leaves unconfirmed
        payment_id = "pay_h6_late"
        sig = hmac.new(_get_key_secret().encode(), f"order_h6|{payment_id}".encode(), hashlib.sha256).hexdigest()
        v_resp = await client.post(
            "/v1/payments/verify",
            json={"booking_id": str(b.id), "razorpay_order_id": "order_h6", "razorpay_payment_id": payment_id, "razorpay_signature": sig},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert v_resp.status_code in (402, 409)

        # Booking remains CANCELLED
        b_final = (await session.execute(select(BookingModel).where(BookingModel.id == b.id))).scalar_one()
        assert b_final.status == "CANCELLED"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# H8: Double order call creates exactly ONE gateway call
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h8_double_order_creates_one_gateway_call(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD", held_until=utcnow() + timedelta(minutes=10))
    session.add(b)
    await session.commit()

    call_count = 0
    async def mock_create_order(amount_paise, currency, receipt):
        nonlocal call_count
        call_count += 1
        return "order_h8_unique"

    monkeypatch.setattr("app.payment.services.gateway_create_order", mock_create_order)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/v1/payments/order", json={"booking_id": str(b.id)}, headers={"Authorization": f"Bearer {token}"})
        r2 = await client.post("/v1/payments/order", json={"booking_id": str(b.id)}, headers={"Authorization": f"Bearer {token}"})

        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["data"]["order_id"] == "order_h8_unique"
        assert r2.json()["data"]["order_id"] == "order_h8_unique"
        assert call_count == 1

        payments_cnt = (await session.execute(select(func.count(PaymentModel.id)).where(PaymentModel.booking_id == b.id))).scalar()
        assert payments_cnt == 1

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# H14: Gateway down during order -> no CREATED row, 502 envelope, retry succeeds
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h14_gateway_down_during_order(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD", held_until=utcnow() + timedelta(minutes=10))
    session.add(b)
    await session.commit()

    should_fail = True
    async def mock_create_order(amount_paise, currency, receipt):
        if should_fail:
            raise GatewayUnavailable("Razorpay network timeout")
        return "order_h14_recovered"

    monkeypatch.setattr("app.payment.services.gateway_create_order", mock_create_order)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Gateway fails -> 502 error envelope
        r1 = await client.post("/v1/payments/order", json={"booking_id": str(b.id)}, headers={"Authorization": f"Bearer {token}"})
        assert r1.status_code == 502
        assert r1.json()["error"]["type"] == "PAYMENT_GATEWAY_UNAVAILABLE"

        # Assert no CREATED row persisted
        payments_cnt = (await session.execute(select(func.count(PaymentModel.id)).where(PaymentModel.booking_id == b.id))).scalar()
        assert payments_cnt == 0

        # 2. Gateway recovers -> retry succeeds
        should_fail = False
        r2 = await client.post("/v1/payments/order", json={"booking_id": str(b.id)}, headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        assert r2.json()["data"]["order_id"] == "order_h14_recovered"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# H17: Valid signature for order A submitted against booking B -> 402 rejected
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h17_valid_signature_wrong_order(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    # Booking A & Payment A
    b_a = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    p_a = PaymentModel(id=uuid.uuid4(), booking_id=b_a.id, order_id="order_A", amount_paise=25000, status="CREATED")

    # Booking B & Payment B
    b_b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    p_b = PaymentModel(id=uuid.uuid4(), booking_id=b_b.id, order_id="order_B", amount_paise=25000, status="CREATED")

    session.add_all([b_a, p_a, b_b, p_b])
    await session.commit()

    # Valid signature for Order A
    payment_id = "pay_replay_17"
    sig_a = hmac.new(_get_key_secret().encode(), f"order_A|{payment_id}".encode(), hashlib.sha256).hexdigest()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Replay: Submit Order A's signature against Booking B
        resp = await client.post(
            "/v1/payments/verify",
            json={"booking_id": str(b_b.id), "razorpay_order_id": "order_A", "razorpay_payment_id": payment_id, "razorpay_signature": sig_a},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 402

        # Neither booking confirmed
        b_a_cur = (await session.execute(select(BookingModel).where(BookingModel.id == b_a.id))).scalar_one()
        b_b_cur = (await session.execute(select(BookingModel).where(BookingModel.id == b_b.id))).scalar_one()
        assert b_a_cur.status == "HELD"
        assert b_b_cur.status == "HELD"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# H23: Stale CREATED payment expires and frees seats on recovery task
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h23_stale_created_expires_and_frees_seats(session: AsyncSession, monkeypatch):
    data = await _seed_self_hosted_data(session)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD", held_until=utcnow() - timedelta(minutes=10))
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h23", amount_paise=25000, status="CREATED", created_at=utcnow() - timedelta(minutes=10))
    ss = SeatState(showtime_id=data["showtime"].id, seat_id=data["seats"][0].id, status="LOCKED", booking_id=b.id, held_until=utcnow() - timedelta(minutes=10))
    session.add_all([p, ss])
    await session.commit()

    from app.booking.repository import BookingRepository, TierCounterRepository
    booking_service = BookingService(BookingRepository(session), TierCounterRepository(session), session)
    from app.movie.repository import MovieRepository
    from app.movie.services import MovieService
    movie_service = MovieService(MovieRepository(session))
    payment_service = PaymentService(PaymentRepository(session), booking_service, session, movie_service)

    # Stub refund tracking
    refund_called = 0
    async def mock_refund(payment_id, amount_paise):
        nonlocal refund_called
        refund_called += 1
        return "rfnd_fake"
    monkeypatch.setattr("app.payment.services.gateway_refund", mock_refund)

    # Run recovery task directly
    result = await payment_service.recovery_task()
    assert result["expired_payments"] >= 1
    assert refund_called == 0

    # Payment row is EXPIRED
    p_updated = (await session.execute(select(PaymentModel).where(PaymentModel.id == p.id))).scalar_one()
    assert p_updated.status == "EXPIRED"

    # Seats are free
    avail = await booking_service.session.execute(
        select(func.count(SeatState.seat_id)).where(SeatState.showtime_id == data["showtime"].id, SeatState.seat_id == data["seats"][0].id)
    )
    assert avail.scalar() == 0


# ---------------------------------------------------------------------------
# H24: Captured payment with failed commit refunds exactly once across multiple runs
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h24_captured_but_commit_fails_refunds_exactly_once(session: AsyncSession, monkeypatch):
    data = await _seed_self_hosted_data(session)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h24", payment_id="pay_h24", amount_paise=25000, status="CAPTURED")
    session.add(p)
    await session.commit()

    refund_call_count = 0
    async def mock_refund(payment_id: str, amount_paise: int) -> str:
        nonlocal refund_call_count
        refund_call_count += 1
        return f"rfnd_{refund_call_count}"

    monkeypatch.setattr("app.payment.services.gateway_refund", mock_refund)

    from app.booking.repository import BookingRepository, TierCounterRepository
    booking_service = BookingService(BookingRepository(session), TierCounterRepository(session), session)
    from app.movie.repository import MovieRepository
    from app.movie.services import MovieService
    movie_service = MovieService(MovieRepository(session))
    payment_service = PaymentService(PaymentRepository(session), booking_service, session, movie_service)

    # Simulate a commit that never succeeds, so the retry-then-refund path
    # under test actually exercises the "3 attempts, then refund" rule.
    async def failing_mark_paid(booking_id, payment_id):
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(booking_service, "mark_paid", failing_mark_paid)

    # Run recovery task 3 times
    res1 = await payment_service.recovery_task()
    res2 = await payment_service.recovery_task()
    res3 = await payment_service.recovery_task()

    # Assert exactly ONE refund call across ALL runs, and not before attempt 3
    assert refund_call_count == 1
    assert res1["refunded_payments"] == 0
    assert res2["refunded_payments"] == 0
    assert res3["refunded_payments"] == 1

    p_updated = (await session.execute(select(PaymentModel).where(PaymentModel.id == p.id))).scalar_one()
    assert p_updated.status == "REFUNDED"
    assert p_updated.refund_id == "rfnd_1"
    b_updated = (await session.execute(select(BookingModel).where(BookingModel.id == b.id))).scalar_one()
    assert b_updated.status == "CANCELLED"


# ---------------------------------------------------------------------------
# H24b: release_expired_locks deletes LOCKED rows while BOOKED survives
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h24b_release_expired_locks_filter(session: AsyncSession):
    data = await _seed_self_hosted_data(session)
    booking_id = uuid.uuid4()

    # 1. Insert a LOCKED seat state and a BOOKED seat state for the same booking_id
    session.add(
        SeatState(
            showtime_id=data["showtime"].id,
            seat_id=data["seats"][0].id,
            status="LOCKED",
            booking_id=booking_id,
            held_until=utcnow() + timedelta(minutes=10),
        )
    )
    session.add(
        SeatState(
            showtime_id=data["showtime"].id,
            seat_id=data["seats"][1].id,
            status="BOOKED",
            booking_id=booking_id,
        )
    )
    await session.commit()

    # 2. Call the new Movie service release_expired_locks method
    from app.movie.repository import MovieRepository
    from app.movie.services import MovieService
    movie_service = MovieService(MovieRepository(session))
    
    rows_deleted = await movie_service.release_expired_locks(booking_id)
    assert rows_deleted == 1

    # 3. Assert the LOCKED row was deleted and the BOOKED row survives
    l_count = (await session.execute(
        select(func.count(SeatState.seat_id)).where(SeatState.booking_id == booking_id, SeatState.status == "LOCKED")
    )).scalar()
    assert l_count == 0

    b_count = (await session.execute(
        select(func.count(SeatState.seat_id)).where(SeatState.booking_id == booking_id, SeatState.status == "BOOKED")
    )).scalar()
    assert b_count == 1


# ---------------------------------------------------------------------------
# H25: commit failure is retried up to 3 times before any refund fires.
# Fails if reverted to refund-on-first-failure behavior.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h27_commit_retried_up_to_three_times_before_refund(session: AsyncSession, monkeypatch):
    data = await _seed_self_hosted_data(session)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h25", payment_id="pay_h25", amount_paise=25000, status="CAPTURED")
    session.add(p)
    await session.commit()

    refund_call_count = 0
    async def mock_refund(payment_id: str, amount_paise: int) -> str:
        nonlocal refund_call_count
        refund_call_count += 1
        return f"rfnd25_{refund_call_count}"
    monkeypatch.setattr("app.payment.services.gateway_refund", mock_refund)

    from app.booking.repository import BookingRepository, TierCounterRepository
    booking_service = BookingService(BookingRepository(session), TierCounterRepository(session), session)
    from app.movie.repository import MovieRepository
    from app.movie.services import MovieService
    movie_service = MovieService(MovieRepository(session))
    payment_service = PaymentService(PaymentRepository(session), booking_service, session, movie_service)

    mark_paid_calls = 0
    async def failing_mark_paid(booking_id, payment_id):
        nonlocal mark_paid_calls
        mark_paid_calls += 1
        raise RuntimeError("simulated commit failure")
    monkeypatch.setattr(booking_service, "mark_paid", failing_mark_paid)

    res1 = await payment_service.recovery_task()
    assert mark_paid_calls == 1
    assert res1["refunded_payments"] == 0
    assert refund_call_count == 0

    res2 = await payment_service.recovery_task()
    assert mark_paid_calls == 2
    assert res2["refunded_payments"] == 0
    assert refund_call_count == 0

    res3 = await payment_service.recovery_task()
    assert mark_paid_calls == 3
    assert res3["refunded_payments"] == 1
    assert refund_call_count == 1

    p_updated = (await session.execute(select(PaymentModel).where(PaymentModel.id == p.id))).scalar_one()
    assert p_updated.status == "REFUNDED"
    assert p_updated.commit_attempts == 3


# ---------------------------------------------------------------------------
# H26: commit succeeds on the second retry -> booking CONFIRMED, no refund,
# never enters CANCELLED. Fails if refund fires before retrying the commit.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_h28_commit_succeeds_on_second_retry_no_refund(session: AsyncSession, monkeypatch):
    data = await _seed_self_hosted_data(session)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h26", payment_id="pay_h26", amount_paise=25000, status="CAPTURED")
    session.add(p)
    await session.commit()

    refund_call_count = 0
    async def mock_refund(payment_id: str, amount_paise: int) -> str:
        nonlocal refund_call_count
        refund_call_count += 1
        return f"rfnd26_{refund_call_count}"
    monkeypatch.setattr("app.payment.services.gateway_refund", mock_refund)

    from app.booking.repository import BookingRepository, TierCounterRepository
    booking_service = BookingService(BookingRepository(session), TierCounterRepository(session), session)
    from app.movie.repository import MovieRepository
    from app.movie.services import MovieService
    movie_service = MovieService(MovieRepository(session))
    payment_service = PaymentService(PaymentRepository(session), booking_service, session, movie_service)

    real_mark_paid = booking_service.mark_paid
    call_count = 0
    async def flaky_mark_paid(booking_id, payment_id):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated transient commit failure")
        return await real_mark_paid(booking_id, payment_id)
    monkeypatch.setattr(booking_service, "mark_paid", flaky_mark_paid)

    res1 = await payment_service.recovery_task()
    assert res1["refunded_payments"] == 0
    assert call_count == 1

    res2 = await payment_service.recovery_task()
    assert res2["refunded_payments"] == 0
    assert call_count == 2

    assert refund_call_count == 0

    b_updated = (await session.execute(select(BookingModel).where(BookingModel.id == b.id))).scalar_one()
    assert b_updated.status == "CONFIRMED"

    p_updated = (await session.execute(select(PaymentModel).where(PaymentModel.id == p.id))).scalar_one()
    assert p_updated.status == "CAPTURED"
    assert p_updated.refund_id is None
