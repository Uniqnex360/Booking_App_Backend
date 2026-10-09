import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock
from httpx import ASGITransport, AsyncClient

from app.booking.interfaces import Booking, BookingStatus, BookingNotFoundError
from app.booking.hold_token import hash_token
from app.booking.dependencies import resolve_actor
from app.booking.routes import _mask_guest_detail
from app.booking.schemas import BaseBookingDetail


@pytest.mark.asyncio
async def test_unauthenticated_cannot_access_confirmed_user_booking():
    booking_service = AsyncMock()
    alice_id = uuid.uuid4()
    booking_id = uuid.uuid4()
    
    alice_booking = Booking(
        id=booking_id,
        user_id=alice_id,
        status=BookingStatus.CONFIRMED,
        showtime_id=uuid.uuid4(),
        provider_id=None,
        total_paise=50000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
        ref_code="ALICE-CONFIRMED-123",
    )
    booking_service.get_booking_for_actor.return_value = alice_booking
    
    # Anonymous caller with no credentials must be rejected with 404/BookingNotFoundError
    with pytest.raises(BookingNotFoundError):
        await resolve_actor(
            booking_id=booking_id,
            x_hold_token=None,
            current_user=None,
            booking_service=booking_service,
        )


@pytest.mark.asyncio
async def test_other_user_cannot_access_confirmed_user_booking():
    booking_service = AsyncMock()
    alice_id = uuid.uuid4()
    bob_id = uuid.uuid4()
    booking_id = uuid.uuid4()
    
    alice_booking = Booking(
        id=booking_id,
        user_id=alice_id,
        status=BookingStatus.CONFIRMED,
        showtime_id=uuid.uuid4(),
        provider_id=None,
        total_paise=50000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
        ref_code="ALICE-CONFIRMED-123",
    )
    booking_service.get_booking_for_actor.return_value = alice_booking
    
    bob_user = AsyncMock()
    bob_user.id = bob_id
    bob_user.role = "USER"
    
    # Bob trying to view Alice's confirmed booking must be rejected with 404
    with pytest.raises(BookingNotFoundError):
        await resolve_actor(
            booking_id=booking_id,
            x_hold_token=None,
            current_user=bob_user,
            booking_service=booking_service,
        )


@pytest.mark.asyncio
async def test_owner_can_access_confirmed_user_booking():
    booking_service = AsyncMock()
    alice_id = uuid.uuid4()
    booking_id = uuid.uuid4()
    
    alice_booking = Booking(
        id=booking_id,
        user_id=alice_id,
        status=BookingStatus.CONFIRMED,
        showtime_id=uuid.uuid4(),
        provider_id=None,
        total_paise=50000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
    )
    booking_service.get_booking_for_actor.return_value = alice_booking
    
    alice_user = AsyncMock()
    alice_user.id = alice_id
    alice_user.role = "USER"
    
    result = await resolve_actor(
        booking_id=booking_id,
        x_hold_token=None,
        current_user=alice_user,
        booking_service=booking_service,
    )
    assert result.id == booking_id
    assert result.actor_role == "OWNER"


@pytest.mark.asyncio
async def test_admin_can_access_any_booking():
    """Admins can view any user or guest booking with full data."""
    booking_service = AsyncMock()
    alice_id = uuid.uuid4()
    booking_id = uuid.uuid4()

    alice_booking = Booking(
        id=booking_id,
        user_id=alice_id,
        status=BookingStatus.CONFIRMED,
        showtime_id=uuid.uuid4(),
        provider_id=None,
        total_paise=50000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
    )
    booking_service.get_booking_for_actor.return_value = alice_booking

    admin_user = AsyncMock()
    admin_user.id = uuid.uuid4()
    admin_user.role = "ADMIN"

    result = await resolve_actor(
        booking_id=booking_id,
        x_hold_token=None,
        current_user=admin_user,
        booking_service=booking_service,
    )
    assert result.id == booking_id
    assert result.actor_role == "ADMIN"


@pytest.mark.asyncio
async def test_guest_with_valid_hold_token_can_access_confirmed_booking():
    booking_service = AsyncMock()
    booking_id = uuid.uuid4()
    raw_hold_token = "valid_guest_secret_hold_token_12345678901234567890"
    
    guest_booking = Booking(
        id=booking_id,
        user_id=None,
        status=BookingStatus.CONFIRMED,
        showtime_id=uuid.uuid4(),
        provider_id=None,
        total_paise=50000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
        hold_token_hash=hash_token(raw_hold_token),
        hold_token_expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    booking_service.get_booking_for_actor.return_value = guest_booking
    
    result = await resolve_actor(
        booking_id=booking_id,
        x_hold_token=raw_hold_token,
        current_user=None,
        booking_service=booking_service,
    )
    assert result.id == booking_id
    assert result.actor_role == "GUEST"


@pytest.mark.asyncio
async def test_guest_with_ref_code_can_access_confirmed_booking():
    booking_service = AsyncMock()
    booking_id = uuid.uuid4()
    
    guest_booking = Booking(
        id=booking_id,
        user_id=None,
        status=BookingStatus.CONFIRMED,
        showtime_id=uuid.uuid4(),
        provider_id=None,
        total_paise=50000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
        ref_code="VYH-GUEST-CONFIRMED",
    )
    booking_service.get_booking_for_actor.return_value = guest_booking
    
    result = await resolve_actor(
        booking_id=booking_id,
        x_hold_token=None,
        current_user=None,
        booking_service=booking_service,
        ref_code="VYH-GUEST-CONFIRMED",
    )
    assert result.id == booking_id
    assert result.actor_role == "GUEST"


@pytest.mark.asyncio
async def test_guest_with_wrong_ref_code_rejected():
    """Guest with incorrect reference code is rejected with 404."""
    booking_service = AsyncMock()
    booking_id = uuid.uuid4()

    guest_booking = Booking(
        id=booking_id,
        user_id=None,
        status=BookingStatus.CONFIRMED,
        showtime_id=uuid.uuid4(),
        provider_id=None,
        total_paise=50000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
        ref_code="VYH-GUEST-CONFIRMED",
    )
    booking_service.get_booking_for_actor.return_value = guest_booking

    with pytest.raises(BookingNotFoundError):
        await resolve_actor(
            booking_id=booking_id,
            x_hold_token=None,
            current_user=None,
            booking_service=booking_service,
            ref_code="WRONG-REF-CODE-999",
        )


@pytest.mark.asyncio
async def test_guest_without_credentials_cannot_access_confirmed_booking():
    booking_service = AsyncMock()
    booking_id = uuid.uuid4()
    
    guest_booking = Booking(
        id=booking_id,
        user_id=None,
        status=BookingStatus.CONFIRMED,
        showtime_id=uuid.uuid4(),
        provider_id=None,
        total_paise=50000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
        ref_code="VYH-GUEST-CONFIRMED",
    )
    booking_service.get_booking_for_actor.return_value = guest_booking
    
    with pytest.raises(BookingNotFoundError):
        await resolve_actor(
            booking_id=booking_id,
            x_hold_token=None,
            current_user=None,
            booking_service=booking_service,
        )


def test_mask_guest_detail_masks_email_and_phone():
    """Guest views have masked email and phone; owner/admin see unmasked data."""
    booking_domain = Booking(
        id=uuid.uuid4(),
        user_id=None,
        status=BookingStatus.CONFIRMED,
        total_paise=50000,
        currency="INR",
        created_at=datetime.now(timezone.utc),
        contact_email="customer@example.com",
        contact_phone="+919876543210",
    )
    detail = BaseBookingDetail.from_domain(booking_domain)
    assert detail.contact_email == "customer@example.com"
    assert detail.contact_phone == "+919876543210"

    masked = _mask_guest_detail(detail)
    assert masked.contact_email == "c******r@example.com"
    assert masked.contact_phone == "+91******3210"
