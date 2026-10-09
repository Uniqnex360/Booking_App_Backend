import pytest
import uuid
from datetime import datetime, timezone, timedelta
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.main import app
from app.core.database import get_db
from app.booking.models import BookingModel


async def _seed_test_bookings(session: AsyncSession):
    # 1. Confirmed guest booking with ref_code
    ref_code = "BKTESTREFCODE123456789012345678"
    confirmed_booking = BookingModel(
        id=uuid.uuid4(),
        user_id=None,
        booking_type="EVENT",
        status="CONFIRMED",
        ref_code=ref_code,
        total_paise=50000,
        currency="INR",
        contact_email="guest@example.com",
        contact_phone="+919876543210",
        created_at=datetime.now(timezone.utc),
    )

    # 2. Held guest booking with ref_code
    held_ref_code = "BKHELDREFCODE123456789012345678"
    held_booking = BookingModel(
        id=uuid.uuid4(),
        user_id=None,
        booking_type="EVENT",
        status="HELD",
        ref_code=held_ref_code,
        total_paise=50000,
        currency="INR",
        held_until=datetime.now(timezone.utc) + timedelta(minutes=10),
        contact_email="held@example.com",
        contact_phone="+919876543210",
        created_at=datetime.now(timezone.utc),
    )

    session.add_all([confirmed_booking, held_booking])
    await session.commit()
    return {
        "confirmed": confirmed_booking,
        "confirmed_ref": ref_code,
        "held": held_booking,
        "held_ref": held_ref_code,
    }


@pytest.mark.asyncio
async def test_read_routes_allow_ref_code(session: AsyncSession):
    """GET /bookings/{id}?ref=... must succeed for read-only viewing."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_bookings(session)
    booking_id = data["confirmed"].id
    ref = data["confirmed_ref"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/bookings/{booking_id}?ref={ref}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == str(booking_id)

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_write_commit_rejects_ref_only_access(session: AsyncSession):
    """POST /bookings/{id}/commit must reject ref-only access with 404."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_bookings(session)
    booking_id = data["held"].id
    ref = data["held_ref"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            f"/v1/bookings/{booking_id}/commit?ref={ref}",
            json={"payment_ref": "pay_fake_123"},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_write_cancel_hold_rejects_ref_only_access(session: AsyncSession):
    """DELETE /bookings/hold/{id} must reject ref-only access with 404."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_bookings(session)
    booking_id = data["held"].id
    ref = data["held_ref"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"/v1/bookings/hold/{booking_id}?ref={ref}")
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_write_cancel_confirmed_rejects_ref_only_access(session: AsyncSession):
    """PATCH /bookings/{id}/cancel must reject ref-only access (401 without auth or 404)."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_bookings(session)
    booking_id = data["confirmed"].id
    ref = data["confirmed_ref"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/v1/bookings/{booking_id}/cancel?ref={ref}")
        assert resp.status_code in (401, 404), f"Expected 401 or 404, got {resp.status_code}"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_write_contact_update_rejects_ref_only_access(session: AsyncSession):
    """PATCH /bookings/{id}/contact must reject ref-only access with 404."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_bookings(session)
    booking_id = data["held"].id
    ref = data["held_ref"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/v1/bookings/{booking_id}/contact?ref={ref}",
            json={"contact_email": "new@example.com", "contact_phone": "+919999999999"},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_write_fnb_update_rejects_ref_only_access(session: AsyncSession):
    """PUT /bookings/{id}/fnb must reject ref-only access with 404."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_bookings(session)
    booking_id = data["held"].id
    ref = data["held_ref"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            f"/v1/bookings/{booking_id}/fnb?ref={ref}",
            json={"items": []},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ref_of_booking_a_on_booking_b_url_returns_404(session: AsyncSession):
    """Using reference code of booking A on URL of booking B must return 404."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_bookings(session)

    # Seed booking B
    booking_b = BookingModel(
        id=uuid.uuid4(),
        user_id=None,
        booking_type="EVENT",
        status="CONFIRMED",
        ref_code="BKOTHERCONFIRMED12345678901234",
        total_paise=50000,
        currency="INR",
        contact_email="other@example.com",
        contact_phone="+919111111111",
        created_at=datetime.now(timezone.utc),
    )
    session.add(booking_b)
    await session.commit()

    ref_a = data["confirmed_ref"]
    url_b = f"/v1/bookings/{booking_b.id}?ref={ref_a}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(url_b)
        print(f"\n[RESPONSE] status_code={resp.status_code}, body={resp.text}")
        assert resp.status_code == 404

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ref_code_get_returns_masked_email_and_phone(session: AsyncSession):
    """Guest lookup with reference code must return masked email and phone."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_bookings(session)
    booking_id = data["confirmed"].id
    ref = data["confirmed_ref"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/bookings/{booking_id}?ref={ref}")
        assert resp.status_code == 200
        body = resp.json()

        # Raw values were guest@example.com and +919876543210
        assert body["contact_email"] != "guest@example.com"
        assert "@example.com" in body["contact_email"]
        assert "*" in body["contact_email"]

        assert body["contact_phone"] != "+919876543210"
        assert "*" in body["contact_phone"]
        assert body["contact_phone"].endswith("3210")

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_guest_confirmation_page_url_e2e_supports_both_ref_and_ref_code(session: AsyncSession):
    """Frontend confirmation URLs using either ?ref= or ?ref_code= succeed identically."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_bookings(session)
    booking_id = data["confirmed"].id
    ref = data["confirmed_ref"]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Frontend OrderSummary / ConfirmationPage standard: ?ref=...
        resp_ref = await client.get(f"/v1/bookings/{booking_id}?ref={ref}")
        assert resp_ref.status_code == 200
        assert resp_ref.json()["id"] == str(booking_id)

        # 2. Alternative parameter name: ?ref_code=...
        resp_ref_code = await client.get(f"/v1/bookings/{booking_id}?ref_code={ref}")
        assert resp_ref_code.status_code == 200
        assert resp_ref_code.json()["id"] == str(booking_id)

    app.dependency_overrides.clear()

