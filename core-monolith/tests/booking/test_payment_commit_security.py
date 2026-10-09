import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from app.booking.interfaces import Booking, BookingStatus, ValidationError
from app.booking.services import BookingService


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
        provider_id="pvr",  # Test on provider showtime too
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
