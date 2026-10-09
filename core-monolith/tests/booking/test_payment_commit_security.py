import pytest
import uuid
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.core.database import get_db
from app.booking.interfaces import Booking, BookingStatus, ValidationError
from app.booking.models import BookingModel
from app.booking.services import BookingService
from app.payment.models import PaymentModel
from app.auth.models import User
from app.auth.security import JWTTokenService


@pytest.fixture
def jwt_service():
    return JWTTokenService()


@pytest.mark.asyncio
async def test_commit_local_movie_without_payment_rejected():
    booking_repo = AsyncMock()
    counter_repo = AsyncMock()
    session = AsyncMock()
    
    booking_id = uuid.uuid4()
    user_id = uuid.uuid4()
    showtime_id = uuid.uuid4()
    
    held_booking = Booking(
        id=booking_id,
        user_id=user_id,
        status=BookingStatus.HELD,
        showtime_id=showtime_id,
        provider_id=None,  # Local movie showtime
        total_paise=35000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
        seat_refs=[uuid.uuid4()],
    )
    booking_repo.get_by_id.return_value = held_booking
    
    # Mock database session returning no captured payment
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    session.execute.return_value = mock_result
    
    service = BookingService(
        booking_repo=booking_repo,
        counter_repo=counter_repo,
        session=session,
    )
    
    # Attempting to commit without payment must fail with ValidationError
    with pytest.raises(ValidationError, match="Payment not verified for this booking"):
        await service.commit_booking(user_id=user_id, booking_id=booking_id, payment_ref=None)
    
    # Ensure update_status was NEVER called to confirm the booking
    booking_repo.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_commit_local_movie_amount_mismatch_rejected():
    booking_repo = AsyncMock()
    counter_repo = AsyncMock()
    session = AsyncMock()
    
    booking_id = uuid.uuid4()
    user_id = uuid.uuid4()
    showtime_id = uuid.uuid4()
    
    held_booking = Booking(
        id=booking_id,
        user_id=user_id,
        status=BookingStatus.HELD,
        showtime_id=showtime_id,
        provider_id=None,
        total_paise=35000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
        seat_refs=[uuid.uuid4()],
    )
    booking_repo.get_by_id.return_value = held_booking
    
    # Mock database session returning captured payment for only 100 paise (tampered amount)
    mock_payment = MagicMock(
        booking_id=booking_id,
        status="CAPTURED",
        amount_paise=100,
        signature_verified=True,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_payment
    session.execute.return_value = mock_result
    
    service = BookingService(
        booking_repo=booking_repo,
        counter_repo=counter_repo,
        session=session,
    )
    
    with pytest.raises(ValidationError, match="Payment amount mismatch"):
        await service.commit_booking(user_id=user_id, booking_id=booking_id, payment_ref=None)
    
    booking_repo.update_status.assert_not_called()


@pytest.mark.asyncio
async def test_commit_booking_is_idempotent():
    booking_repo = AsyncMock()
    counter_repo = AsyncMock()
    session = AsyncMock()
    
    booking_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    confirmed_booking = Booking(
        id=booking_id,
        user_id=user_id,
        status=BookingStatus.CONFIRMED,
        showtime_id=uuid.uuid4(),
        provider_id=None,
        total_paise=25000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
    )
    booking_repo.get_by_id.return_value = confirmed_booking
    
    service = BookingService(
        booking_repo=booking_repo,
        counter_repo=counter_repo,
        session=session,
    )
    
    # Re-committing an already confirmed booking must return it without error
    result = await service.commit_booking(user_id=user_id, booking_id=booking_id, payment_ref="pay_123")
    assert result.status == BookingStatus.CONFIRMED
    assert result.id == booking_id


@pytest.mark.asyncio
async def test_post_commit_empty_body_rejected_with_402(session, jwt_service):
    """Proves original bypass is closed: POST commit with empty body fails with 402."""
    user = User(id=uuid.uuid4(), full_name="Customer", email="buyer@example.com")
    booking_id = uuid.uuid4()
    booking_orm = BookingModel(
        id=booking_id,
        user_id=user.id,
        booking_type="EVENT",
        event_id=uuid.uuid4(),
        tier_id=uuid.uuid4(),
        status="HELD",
        total_paise=50000,
        ref_code=f"BK{uuid.uuid4().hex[:8].upper()}",
    )
    session.add_all([user, booking_orm])
    await session.commit()

    token = jwt_service.create_access_token(user)

    app.dependency_overrides[get_db] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                f"/v1/bookings/{booking_id}/commit",
                json={},  # Empty body: no payment ref, and no captured payment in DB
                headers={"Authorization": f"Bearer {token}"},
            )
            assert resp.status_code == 402
            data = resp.json()
            assert data["error"]["type"] == "PAYMENT_VERIFICATION_FAILED"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_commit_zero_total_booking_succeeds_without_payment():
    """Zero-total booking (e.g. 100% coupon or free tier) commits without payment."""
    booking_repo = AsyncMock()
    counter_repo = AsyncMock()
    session = AsyncMock()

    booking_id = uuid.uuid4()
    user_id = uuid.uuid4()
    tier_id = uuid.uuid4()

    held_zero_booking = Booking(
        id=booking_id,
        user_id=user_id,
        status=BookingStatus.HELD,
        tier_id=tier_id,
        total_paise=0,  # Free / fully discounted
        currency="INR",
        created_at=datetime.now(timezone.utc),
    )
    confirmed_zero_booking = Booking(
        id=booking_id,
        user_id=user_id,
        status=BookingStatus.CONFIRMED,
        tier_id=tier_id,
        total_paise=0,
        currency="INR",
        created_at=datetime.now(timezone.utc),
    )

    booking_repo.get_by_id.side_effect = [held_zero_booking, confirmed_zero_booking]
    booking_repo.update_status.return_value = True

    service = BookingService(
        booking_repo=booking_repo,
        counter_repo=counter_repo,
        session=session,
    )

    result = await service.commit_booking(user_id=user_id, booking_id=booking_id, payment_ref=None)
    assert result.status == BookingStatus.CONFIRMED
    booking_repo.update_status.assert_awaited_once_with(
        booking_id, BookingStatus.HELD, BookingStatus.CONFIRMED
    )


@pytest.mark.asyncio
async def test_commit_concurrency_lock_and_idempotence():
    """Parallel commit requests on the same booking result in exactly one confirmation."""
    booking_repo = AsyncMock()
    counter_repo = AsyncMock()
    session = AsyncMock()

    booking_id = uuid.uuid4()
    user_id = uuid.uuid4()

    held_booking = Booking(
        id=booking_id,
        user_id=user_id,
        status=BookingStatus.HELD,
        tier_id=uuid.uuid4(),
        total_paise=10000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
    )
    confirmed_booking = Booking(
        id=booking_id,
        user_id=user_id,
        status=BookingStatus.CONFIRMED,
        tier_id=held_booking.tier_id,
        total_paise=10000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
    )

    # Simulate atomic update: first call returns True, second returns False (already confirmed)
    state = {"status": BookingStatus.HELD, "updates": 0}

    async def mock_get_by_id(b_id, for_update=False):
        if state["status"] == BookingStatus.CONFIRMED:
            return confirmed_booking
        return held_booking

    async def mock_update_status(b_id, old_st, new_st):
        if state["status"] == BookingStatus.HELD:
            state["status"] = BookingStatus.CONFIRMED
            state["updates"] += 1
            return True
        return False

    booking_repo.get_by_id.side_effect = mock_get_by_id
    booking_repo.update_status.side_effect = mock_update_status

    # Mock captured payment
    mock_payment = MagicMock(
        booking_id=booking_id,
        status="CAPTURED",
        amount_paise=10000,
        signature_verified=True,
    )
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = mock_payment
    session.execute.return_value = mock_result

    service = BookingService(
        booking_repo=booking_repo,
        counter_repo=counter_repo,
        session=session,
    )

    # Run 5 parallel commits concurrently
    tasks = [
        service.commit_booking(user_id=user_id, booking_id=booking_id, payment_ref="pay_123")
        for _ in range(5)
    ]
    results = await asyncio.gather(*tasks)

    # All parallel calls must resolve to CONFIRMED
    assert all(r.status == BookingStatus.CONFIRMED for r in results)
    # The underlying status transition must have happened exactly once
    assert state["updates"] == 1


@pytest.mark.asyncio
async def test_commit_rejects_captured_payment_from_different_booking(session, jwt_service):
    """Captured payment from booking X with same amount cannot be used to confirm booking Y."""
    user = User(id=uuid.uuid4(), full_name="Customer", email="buyer2@example.com")
    session.add(user)

    # Booking X (Confirmed with a captured payment)
    booking_x_id = uuid.uuid4()
    booking_x = BookingModel(
        id=booking_x_id,
        user_id=user.id,
        booking_type="EVENT",
        event_id=uuid.uuid4(),
        tier_id=uuid.uuid4(),
        status="CONFIRMED",
        total_paise=50000,
        ref_code=f"BK{uuid.uuid4().hex[:8].upper()}",
    )
    session.add(booking_x)
    await session.flush()

    payment_x = PaymentModel(
        id=uuid.uuid4(),
        booking_id=booking_x_id,
        order_id="order_x_12345",
        payment_id="pay_x_captured_500",
        amount_paise=50000,
        currency="INR",
        status="CAPTURED",
        signature_verified=True,
    )
    session.add(payment_x)

    # Booking Y (Held, needing payment)
    booking_y_id = uuid.uuid4()
    booking_y = BookingModel(
        id=booking_y_id,
        user_id=user.id,
        booking_type="EVENT",
        event_id=uuid.uuid4(),
        tier_id=uuid.uuid4(),
        status="HELD",
        total_paise=50000,
        ref_code=f"BK{uuid.uuid4().hex[:8].upper()}",
    )
    session.add(booking_y)
    await session.commit()

    token = jwt_service.create_access_token(user)

    # Mock Razorpay gateway API returning valid captured payment for pay_x_captured_500
    mock_rzp_resp = MagicMock()
    mock_rzp_resp.status_code = 200
    mock_rzp_resp.json.return_value = {
        "id": "pay_x_captured_500",
        "amount": 50000,
        "currency": "INR",
        "status": "captured",
        "order_id": "order_x_12345",
        "notes": {"booking_id": str(booking_x_id)},
    }

    app.dependency_overrides[get_db] = lambda: session
    try:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_rzp_resp
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/v1/bookings/{booking_y_id}/commit",
                    json={"payment_ref": "pay_x_captured_500"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 402, f"Expected 402, got {resp.status_code}: {resp.text}"
                assert resp.json()["error"]["type"] == "PAYMENT_VERIFICATION_FAILED"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_commit_fails_closed_when_notes_missing(session, jwt_service):
    """Fallback gateway commit fails closed if notes or order_id missing."""
    user = User(id=uuid.uuid4(), full_name="Customer", email="buyer3@example.com")
    session.add(user)

    booking_id = uuid.uuid4()
    booking = BookingModel(
        id=booking_id,
        user_id=user.id,
        booking_type="EVENT",
        event_id=uuid.uuid4(),
        tier_id=uuid.uuid4(),
        status="HELD",
        total_paise=50000,
        ref_code=f"BK{uuid.uuid4().hex[:8].upper()}",
    )
    session.add(booking)
    await session.commit()

    token = jwt_service.create_access_token(user)

    # Missing notes entirely
    mock_rzp_resp = MagicMock()
    mock_rzp_resp.status_code = 200
    mock_rzp_resp.json.return_value = {
        "id": "pay_missing_notes",
        "amount": 50000,
        "currency": "INR",
        "status": "captured",
        "order_id": "order_missing_notes",
        # notes omitted
    }

    app.dependency_overrides[get_db] = lambda: session
    try:
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_rzp_resp
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post(
                    f"/v1/bookings/{booking_id}/commit",
                    json={"payment_ref": "pay_missing_notes"},
                    headers={"Authorization": f"Bearer {token}"},
                )
                assert resp.status_code == 402, f"Expected 402, got {resp.status_code}: {resp.text}"
                assert resp.json()["error"]["type"] == "PAYMENT_VERIFICATION_FAILED"
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_concurrent_commits_with_same_payment_id_one_wins(engine, jwt_service):
    """Two concurrent commits on different bookings with one payment id: exactly one wins."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    user_id = uuid.uuid4()
    booking1_id = uuid.uuid4()
    booking2_id = uuid.uuid4()
    order1_id = f"order_{uuid.uuid4().hex[:12]}"
    order2_id = f"order_{uuid.uuid4().hex[:12]}"
    shared_pay_id = f"pay_{uuid.uuid4().hex[:14]}"

    async with factory() as s:
        user = User(id=user_id, full_name="Concurrent Tester", email="concur@example.com")
        s.add(user)
        b1 = BookingModel(
            id=booking1_id,
            user_id=user_id,
            booking_type="EVENT",
            event_id=uuid.uuid4(),
            tier_id=uuid.uuid4(),
            status="HELD",
            total_paise=30000,
            ref_code=f"BK{uuid.uuid4().hex[:8].upper()}",
        )
        b2 = BookingModel(
            id=booking2_id,
            user_id=user_id,
            booking_type="EVENT",
            event_id=uuid.uuid4(),
            tier_id=uuid.uuid4(),
            status="HELD",
            total_paise=30000,
            ref_code=f"BK{uuid.uuid4().hex[:8].upper()}",
        )
        p1 = PaymentModel(
            id=uuid.uuid4(),
            booking_id=booking1_id,
            order_id=order1_id,
            amount_paise=30000,
            currency="INR",
            status="CREATED",
        )
        p2 = PaymentModel(
            id=uuid.uuid4(),
            booking_id=booking2_id,
            order_id=order2_id,
            amount_paise=30000,
            currency="INR",
            status="CREATED",
        )
        s.add_all([b1, b2, p1, p2])
        await s.commit()

    token = jwt_service.create_access_token(user)

    import contextvars
    import httpx
    current_commit_ctx = contextvars.ContextVar("current_commit_ctx")

    async def attempt_commit(booking_id: uuid.UUID, order_id: str):
        current_commit_ctx.set((booking_id, order_id))
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                f"/v1/bookings/{booking_id}/commit",
                json={"payment_ref": shared_pay_id},
                headers={"Authorization": f"Bearer {token}"},
            )

    real_async_get = httpx.AsyncClient.get

    async def mock_razorpay_get(url, *args, **kwargs):
        if "api.razorpay.com" in str(url):
            b_id, o_id = current_commit_ctx.get()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {
                "id": shared_pay_id,
                "amount": 30000,
                "currency": "INR",
                "status": "captured",
                "order_id": o_id,
                "notes": {"booking_id": str(b_id)},
            }
            return mock_resp
        return await real_async_get(url, *args, **kwargs)

    async def override_get_db():
        async with factory() as req_session:
            yield req_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with patch("httpx.AsyncClient.get", side_effect=mock_razorpay_get):
            # Launch both commits concurrently
            res1, res2 = await asyncio.gather(
                attempt_commit(booking1_id, order1_id),
                attempt_commit(booking2_id, order2_id),
            )
    finally:
        app.dependency_overrides.pop(get_db, None)

    statuses = [res1.status_code, res2.status_code]
    # Exactly one must succeed (200) and the other must fail (not 200)
    assert statuses.count(200) == 1, f"Expected exactly one 200, got {statuses}: {res1.text} vs {res2.text}"
    assert all(st in (200, 400, 402, 409) for st in statuses)




