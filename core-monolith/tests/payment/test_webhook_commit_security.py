"""
Security and idempotency tests for Razorpay webhook and commit/verify flows.
Covers:
- Webhook confirming a HELD booking with no user (guest booking) under commit rules.
- Webhook followed by verify (exactly one confirmation, zero errors).
- Verify followed by webhook (exactly one confirmation, zero errors).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.booking.models import BookingModel
from app.core.database import get_db
from app.main import app
from app.movie.models import Movie, Screen, ScreenRow, Seat, SeatState, Showtime, Venue
from app.payment.gateway import _get_key_secret, _get_webhook_secret
from app.payment.models import PaymentModel
from app.booking.hold_token import hash_token
from app.shared.timeutil import utcnow


async def _seed_test_showtime_and_seats(session: AsyncSession) -> dict:
    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="Metro Cinema", city="Kochi", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Audi 1")
    movie = Movie(id=uuid.uuid4(), title="Inception", duration_min=148, language="English", certificate="UA", status="PUBLISHED", partner_id=partner_id)
    session.add_all([venue, screen, movie])
    await session.flush()

    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=10, price_paise=25000)
    session.add(row)
    await session.flush()

    st = Showtime(
        id=uuid.uuid4(),
        screen_id=screen.id,
        movie_id=movie.id,
        starts_at=utcnow() + timedelta(days=1),
        partner_id=partner_id,
        provider_id=None,
    )
    session.add(st)
    await session.flush()

    seat = Seat(id=uuid.uuid4(), row_id=row.id, number=1, code="A01", x=0)
    session.add(seat)
    await session.commit()

    return {"showtime": st, "seat": seat}


def _make_webhook_payload(order_id: str, payment_id: str, event_id: str | None = None) -> tuple[bytes, str]:
    body_dict = {
        "id": event_id or f"evt_{uuid.uuid4().hex[:12]}",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                }
            }
        },
    }
    raw_bytes = json.dumps(body_dict).encode("utf-8")
    sig = hmac.new(_get_webhook_secret().encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    return raw_bytes, sig


def _make_verify_signature(order_id: str, payment_id: str) -> str:
    msg = f"{order_id}|{payment_id}"
    return hmac.new(_get_key_secret().encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


@pytest.mark.asyncio
async def test_webhook_confirms_guest_held_booking(session: AsyncSession):
    """Webhook confirms a guest HELD booking (user_id=None) under commit rules."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_showtime_and_seats(session)

    booking_id = uuid.uuid4()
    order_id = f"order_guest_{uuid.uuid4().hex[:8]}"
    payment_id = f"pay_guest_{uuid.uuid4().hex[:8]}"
    raw_hold_token = f"ht_{uuid.uuid4().hex}"

    booking = BookingModel(
        id=booking_id,
        user_id=None,  # Guest booking - no user
        booking_type="MOVIE",
        showtime_id=data["showtime"].id,
        total_paise=25000,
        status="HELD",
        held_until=utcnow() + timedelta(minutes=10),
        hold_token_hash=hash_token(raw_hold_token),
        hold_token_expires_at=utcnow() + timedelta(minutes=10),
        contact_email="guest@example.com",
        contact_phone="+919876543210",
        seat_refs_json=json.dumps([str(data["seat"].id)]),
    )
    session.add(booking)
    await session.flush()

    payment = PaymentModel(
        id=uuid.uuid4(),
        booking_id=booking_id,
        gateway="RAZORPAY",
        order_id=order_id,
        amount_paise=25000,
        status="CREATED",
        currency="INR",
    )
    seat_lock = SeatState(
        showtime_id=data["showtime"].id,
        seat_id=data["seat"].id,
        status="LOCKED",
        booking_id=booking_id,
        held_until=utcnow() + timedelta(minutes=10),
    )
    session.add_all([payment, seat_lock])
    await session.commit()

    raw_bytes, sig = _make_webhook_payload(order_id, payment_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/webhooks/razorpay",
            content=raw_bytes,
            headers={"X-Razorpay-Signature": sig},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    # Verify booking is CONFIRMED and remains guest-owned
    b_row = (await session.execute(select(BookingModel).where(BookingModel.id == booking_id))).scalar_one()
    assert b_row.status == "CONFIRMED"
    assert b_row.user_id is None

    # Verify payment is CAPTURED and signature verified
    p_row = (await session.execute(select(PaymentModel).where(PaymentModel.booking_id == booking_id))).scalar_one()
    assert p_row.status == "CAPTURED"
    assert p_row.signature_verified is True
    assert p_row.payment_id == payment_id

    # Verify seats are BOOKED
    s_row = (await session.execute(select(SeatState).where(SeatState.booking_id == booking_id))).scalar_one()
    assert s_row.status == "BOOKED"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_webhook_then_verify_idempotency(session: AsyncSession, monkeypatch):
    """Test webhook first, then client verify: exactly one confirmation, zero errors."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_showtime_and_seats(session)

    booking_id = uuid.uuid4()
    order_id = f"order_wh_ver_{uuid.uuid4().hex[:8]}"
    payment_id = f"pay_wh_ver_{uuid.uuid4().hex[:8]}"
    raw_hold_token = f"ht_{uuid.uuid4().hex}"

    booking = BookingModel(
        id=booking_id,
        user_id=None,
        booking_type="MOVIE",
        showtime_id=data["showtime"].id,
        total_paise=25000,
        status="HELD",
        held_until=utcnow() + timedelta(minutes=10),
        hold_token_hash=hash_token(raw_hold_token),
        hold_token_expires_at=utcnow() + timedelta(minutes=10),
        contact_email="guest2@example.com",
        contact_phone="+919876543211",
        seat_refs_json=json.dumps([str(data["seat"].id)]),
    )
    session.add(booking)
    await session.flush()

    payment = PaymentModel(
        id=uuid.uuid4(),
        booking_id=booking_id,
        gateway="RAZORPAY",
        order_id=order_id,
        amount_paise=25000,
        status="CREATED",
        currency="INR",
    )
    seat_lock = SeatState(
        showtime_id=data["showtime"].id,
        seat_id=data["seat"].id,
        status="LOCKED",
        booking_id=booking_id,
        held_until=utcnow() + timedelta(minutes=10),
    )
    session.add_all([payment, seat_lock])
    await session.commit()

    # Step 1: Webhook arrives first
    raw_bytes, sig = _make_webhook_payload(order_id, payment_id)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        wh_resp = await client.post(
            "/v1/webhooks/razorpay",
            content=raw_bytes,
            headers={"X-Razorpay-Signature": sig},
        )
        assert wh_resp.status_code == 200

        # Booking is now confirmed
        b_after_wh = (await session.execute(select(BookingModel).where(BookingModel.id == booking_id))).scalar_one()
        assert b_after_wh.status == "CONFIRMED"

        # Step 2: Client calls verify after webhook already confirmed
        verify_sig = _make_verify_signature(order_id, payment_id)
        ver_resp = await client.post(
            "/v1/payments/verify",
            json={
                "booking_id": str(booking_id),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": verify_sig,
            },
            headers={"X-Hold-Token": raw_hold_token},
        )
        assert ver_resp.status_code == 200
        assert ver_resp.json()["data"]["status"] == "PAID"

    # Status remains CONFIRMED (no duplicate side effects or transitions)
    b_final = (await session.execute(select(BookingModel).where(BookingModel.id == booking_id))).scalar_one()
    assert b_final.status == "CONFIRMED"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_verify_then_webhook_idempotency(session: AsyncSession, monkeypatch):
    """Test client verify first, then webhook arrives: exactly one confirmation, zero errors."""
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_test_showtime_and_seats(session)

    booking_id = uuid.uuid4()
    order_id = f"order_ver_wh_{uuid.uuid4().hex[:8]}"
    payment_id = f"pay_ver_wh_{uuid.uuid4().hex[:8]}"
    raw_hold_token = f"ht_{uuid.uuid4().hex}"

    booking = BookingModel(
        id=booking_id,
        user_id=None,
        booking_type="MOVIE",
        showtime_id=data["showtime"].id,
        total_paise=25000,
        status="HELD",
        held_until=utcnow() + timedelta(minutes=10),
        hold_token_hash=hash_token(raw_hold_token),
        hold_token_expires_at=utcnow() + timedelta(minutes=10),
        contact_email="guest3@example.com",
        contact_phone="+919876543212",
        seat_refs_json=json.dumps([str(data["seat"].id)]),
    )
    session.add(booking)
    await session.flush()

    payment = PaymentModel(
        id=uuid.uuid4(),
        booking_id=booking_id,
        gateway="RAZORPAY",
        order_id=order_id,
        amount_paise=25000,
        status="CREATED",
        currency="INR",
    )
    seat_lock = SeatState(
        showtime_id=data["showtime"].id,
        seat_id=data["seat"].id,
        status="LOCKED",
        booking_id=booking_id,
        held_until=utcnow() + timedelta(minutes=10),
    )
    session.add_all([payment, seat_lock])
    await session.commit()

    # Mock gateway fetch
    async def mock_fetch_payment(pid):
        return {"id": pid, "status": "captured"}
    monkeypatch.setattr("app.payment.services.gateway_fetch_payment", mock_fetch_payment)

    verify_sig = _make_verify_signature(order_id, payment_id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Step 1: Client calls verify first
        ver_resp = await client.post(
            "/v1/payments/verify",
            json={
                "booking_id": str(booking_id),
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": verify_sig,
            },
            headers={"X-Hold-Token": raw_hold_token},
        )
        assert ver_resp.status_code == 200
        assert ver_resp.json()["data"]["status"] == "PAID"

        b_after_ver = (await session.execute(select(BookingModel).where(BookingModel.id == booking_id))).scalar_one()
        assert b_after_ver.status == "CONFIRMED"

        # Step 2: Webhook arrives after verify
        raw_bytes, sig = _make_webhook_payload(order_id, payment_id)
        wh_resp = await client.post(
            "/v1/webhooks/razorpay",
            content=raw_bytes,
            headers={"X-Razorpay-Signature": sig},
        )
        assert wh_resp.status_code == 200
        assert wh_resp.json()["status"] == "ok"

    # Status remains CONFIRMED
    b_final = (await session.execute(select(BookingModel).where(BookingModel.id == booking_id))).scalar_one()
    assert b_final.status == "CONFIRMED"

    app.dependency_overrides.clear()
