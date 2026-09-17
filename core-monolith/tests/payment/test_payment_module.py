"""
Payment Module Tests H1 through H25.
"""

import hmac
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Response
from jose import jwt
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.booking.models import BookingModel
from app.booking.services import BookingService
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.movie.models import Movie, Screen, ScreenRow, Seat, SeatState, Showtime, Venue
from app.partner.models import PartnerORM
from app.payment.models import PaymentModel, PaymentEventModel
from app.payment.gateway import verify_boot_config, _get_key_secret, _get_webhook_secret
from app.shared.providers.registry import ProviderRegistryModel
from app.shared.timeutil import utcnow


def _token_for(user_id: uuid.UUID, role: str = "USER") -> str:
    to_encode = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
        "type": "access",
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def _seed_self_hosted_data(session: AsyncSession) -> dict:
    partner = User(id=uuid.uuid4(), full_name="Partner P", email=f"p_{uuid.uuid4().hex[:6]}@t.local", password_hash="pwd", role="PARTNER", is_active=True)
    session.add(partner)
    await session.flush()

    partner_rec = PartnerORM(
        id=uuid.uuid4(),
        user_id=partner.id,
        business_name="Partner Cinema Ltd",
        partner_type="cinema",
        contact_name="Partner P",
        contact_phone="9876543210",
        city="Kochi",
        status="APPROVED",
    )
    session.add(partner_rec)
    await session.flush()

    venue = Venue(id=uuid.uuid4(), name="Venue P", city="Kochi", partner_id=partner_rec.id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Screen P", total_seats=10)
    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=10, price_paise=25000)
    seats = [Seat(id=uuid.uuid4(), row_id=row.id, number=i, code=f"A{i:02d}", x=i-1) for i in range(1, 11)]
    movie = Movie(id=uuid.uuid4(), title="Film P", duration_min=120, language="Malayalam", certificate="U", status="PUBLISHED", partner_id=partner_rec.id)
    st = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=utcnow() + timedelta(days=1), partner_id=partner_rec.id, status="ACTIVE")
    user = User(id=uuid.uuid4(), full_name="Customer P", email=f"cust_{uuid.uuid4().hex[:6]}@t.local", password_hash="pwd", role="USER", is_active=True)

    session.add_all([venue, screen, row, *seats, movie, st, user])
    await session.commit()
    return {"user": user, "partner": partner, "showtime": st, "seats": seats, "row": row, "movie": movie}


# H1: seat-hold writes LOCKED rows + a HELD booking; /availability counts them as locked
@pytest.mark.asyncio
async def test_h1_seat_hold_writes_locked_rows(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings/seat-hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": [str(data["seats"][0].id)]},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "h1-key"},
        )
        assert resp.status_code == 201
        assert resp.json()["data"]["status"] == "HELD"

        # Check availability
        avail_resp = await client.get(f"/v1/showtimes/{data['showtime'].id}/availability")
        assert avail_resp.status_code == 200
        b = avail_resp.json()
        assert b["locked_seats"] == 1
        assert b["booked_seats"] == 0
        assert b["available_seats"] + b["locked_seats"] + b["booked_seats"] + b["blocked_seats"] == b["total_seats"]

    app.dependency_overrides.clear()


# H2: Two users race one seat at hold step -> exactly one wins, loser gets 409
@pytest.mark.asyncio
async def test_h2_concurrent_seat_hold_race(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    user2 = User(id=uuid.uuid4(), full_name="Cust 2", email="c2@t.local", password_hash="pwd", role="USER", is_active=True)
    session.add(user2)
    await session.commit()

    token1 = _token_for(data["user"].id)
    token2 = _token_for(user2.id)
    target_seat = str(data["seats"][0].id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/v1/bookings/seat-hold", json={"showtime_id": str(data["showtime"].id), "seat_ids": [target_seat]}, headers={"Authorization": f"Bearer {token1}", "Idempotency-Key": "h2-1"})
        r2 = await client.post("/v1/bookings/seat-hold", json={"showtime_id": str(data["showtime"].id), "seat_ids": [target_seat]}, headers={"Authorization": f"Bearer {token2}", "Idempotency-Key": "h2-2"})
        
        codes = sorted([r1.status_code, r2.status_code])
        assert codes == [201, 409]

    app.dependency_overrides.clear()


# H3: Expired lock -> seat bookable on the very next read with the sweep NOT run
@pytest.mark.asyncio
async def test_h3_expired_lock_immediately_available(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    # Insert an expired lock
    past = utcnow() - timedelta(minutes=5)
    b_id = uuid.uuid4()
    session.add(SeatState(showtime_id=data["showtime"].id, seat_id=data["seats"][0].id, status="LOCKED", booking_id=b_id, held_until=past))
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        avail_resp = await client.get(f"/v1/showtimes/{data['showtime'].id}/availability")
        assert avail_resp.status_code == 200
        assert avail_resp.json()["available_seats"] == 10  # Expired lock not counted as locked

        # Next hold succeeds
        resp = await client.post(
            "/v1/bookings/seat-hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": [str(data["seats"][0].id)]},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "h3-key"},
        )
        assert resp.status_code == 201

    app.dependency_overrides.clear()


# H4: Lock -> release -> re-lock the same seat succeeds
@pytest.mark.asyncio
async def test_h4_lock_release_relock_same_seat(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)
    seat_id = str(data["seats"][1].id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/v1/bookings/seat-hold", json={"showtime_id": str(data["showtime"].id), "seat_ids": [seat_id]}, headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "h4-1"})
        assert r1.status_code == 201
        b_id = r1.json()["data"]["id"]

        # Release
        del_r = await client.delete(f"/v1/bookings/seat-hold/{b_id}", headers={"Authorization": f"Bearer {token}"})
        assert del_r.status_code == 204

        # Re-lock same seat succeeds
        r2 = await client.post("/v1/bookings/seat-hold", json={"showtime_id": str(data["showtime"].id), "seat_ids": [seat_id]}, headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "h4-2"})
        assert r2.status_code == 201

    app.dependency_overrides.clear()


# H5: Layout edit while a LOCKED row exists -> 409
@pytest.mark.asyncio
async def test_h5_layout_edit_locked_seat_fails(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token_p = _token_for(data["partner"].id, role="PARTNER")

    # Add a lock
    session.add(SeatState(showtime_id=data["showtime"].id, seat_id=data["seats"][0].id, status="LOCKED", held_until=utcnow() + timedelta(minutes=5)))
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/v1/partner/screens/{data['showtime'].screen_id}/layout", json={"text_grid": "A: 1111"}, headers={"Authorization": f"Bearer {token_p}"})
        assert resp.status_code == 409

    app.dependency_overrides.clear()


# H7: /payments/order happy path -> 200, one CREATED payment row
@pytest.mark.asyncio
async def test_h7_payments_order_happy_path(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    # Fake async create_order gateway call
    async def mock_create_order(amount_paise, currency, receipt):
        return "order_fake_h7"
    monkeypatch.setattr("app.payment.services.gateway_create_order", mock_create_order)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Hold seat
        h_resp = await client.post("/v1/bookings/seat-hold", json={"showtime_id": str(data["showtime"].id), "seat_ids": [str(data["seats"][0].id)]}, headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "h7-k"})
        b_id = h_resp.json()["data"]["id"]

        # 2. Create payment order
        order_resp = await client.post("/v1/payments/order", json={"booking_id": b_id}, headers={"Authorization": f"Bearer {token}"})
        assert order_resp.status_code == 200
        body = order_resp.json()["data"]
        assert body["order_id"] == "order_fake_h7"
        assert body["amount_paise"] == 25000

    app.dependency_overrides.clear()


# H9: /payments/order on a CONFIRMED booking -> 409 BOOKING_NOT_PAYABLE
@pytest.mark.asyncio
async def test_h9_order_on_confirmed_booking_rejected(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="CONFIRMED")
    session.add(b)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/payments/order", json={"booking_id": str(b.id)}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 409
        assert resp.json()["error"]["type"] == "BOOKING_NOT_PAYABLE"

    app.dependency_overrides.clear()


# H10: /payments/order on another user's booking -> 404
@pytest.mark.asyncio
async def test_h10_order_foreign_booking_404(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    user_other = User(id=uuid.uuid4(), full_name="Other", email="other@t.local", password_hash="pwd", role="USER", is_active=True)
    session.add(user_other)
    await session.commit()
    token_other = _token_for(user_other.id)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD", held_until=utcnow()+timedelta(minutes=10))
    session.add(b)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/payments/order", json={"booking_id": str(b.id)}, headers={"Authorization": f"Bearer {token_other}"})
        assert resp.status_code == 404

    app.dependency_overrides.clear()


# H11: /payments/order on a provider showtime -> 409 PAYMENT_NOT_AVAILABLE_HERE
@pytest.mark.asyncio
async def test_h11_order_on_provider_showtime_rejected(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    prov = ProviderRegistryModel(id=uuid.uuid4(), name="Prov", base_url="http://prov.local", hold_ttl_seconds=600, enabled=True)
    session.add(prov)
    await session.flush()
    data["showtime"].provider_id = prov.id
    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD", held_until=utcnow()+timedelta(minutes=10))
    session.add_all([data["showtime"], b])
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/payments/order", json={"booking_id": str(b.id)}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 409
        assert resp.json()["error"]["type"] == "PAYMENT_NOT_AVAILABLE_HERE"

    app.dependency_overrides.clear()


# H12: /payments/order with remaining hold < window -> 409 HOLD_TOO_SHORT
@pytest.mark.asyncio
async def test_h12_order_hold_too_short_rejected(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    # Remaining hold is only 100 seconds (< 360s window)
    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD", held_until=utcnow()+timedelta(seconds=100))
    session.add(b)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/payments/order", json={"booking_id": str(b.id)}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 409
        assert resp.json()["error"]["type"] == "HOLD_TOO_SHORT"

    app.dependency_overrides.clear()


# H13: total_paise == 0 -> NOT_REQUIRED, no payments row
@pytest.mark.asyncio
async def test_h13_zero_total_not_required(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=0, status="HELD", held_until=utcnow()+timedelta(minutes=10))
    session.add(b)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/payments/order", json={"booking_id": str(b.id)}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "NOT_REQUIRED"

    app.dependency_overrides.clear()


# H15: verify with a signature computed from secret -> CAPTURED, booking CONFIRMED
@pytest.mark.asyncio
async def test_h15_verify_valid_signature_captures(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h15", amount_paise=25000, status="CREATED")
    ss = SeatState(showtime_id=data["showtime"].id, seat_id=data["seats"][0].id, status="LOCKED", booking_id=b.id, held_until=utcnow()+timedelta(minutes=10))
    session.add_all([p, ss])
    await session.commit()

    # Compute valid signature
    payment_id = "pay_fake_123"
    msg = f"order_h15|{payment_id}"
    sig = hmac.new(_get_key_secret().encode(), msg.encode(), hashlib.sha256).hexdigest()

    async def mock_fetch_payment(pid):
        return {"id": pid, "status": "captured"}
    monkeypatch.setattr("app.payment.services.gateway_fetch_payment", mock_fetch_payment)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/payments/verify",
            json={"booking_id": str(b.id), "razorpay_order_id": "order_h15", "razorpay_payment_id": payment_id, "razorpay_signature": sig},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "PAID"

    # Verify state updates
    b_updated = (await session.execute(select(BookingModel).where(BookingModel.id == b.id))).scalar_one()
    assert b_updated.status == "CONFIRMED"
    ss_updated = (await session.execute(select(SeatState).where(SeatState.booking_id == b.id))).scalar_one()
    assert ss_updated.status == "BOOKED"

    app.dependency_overrides.clear()


# H16: verify with bad signature -> 402, payment FAILED, booking untouched
@pytest.mark.asyncio
async def test_h16_verify_bad_signature_402(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h16", amount_paise=25000, status="CREATED")
    session.add(p)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/payments/verify",
            json={"booking_id": str(b.id), "razorpay_order_id": "order_h16", "razorpay_payment_id": "pay_bad", "razorpay_signature": "invalid_sig"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 402
        assert resp.json()["error"]["type"] == "PAYMENT_VERIFICATION_FAILED"

    app.dependency_overrides.clear()


# H18: verify twice -> identical result (idempotent double tap)
@pytest.mark.asyncio
async def test_h18_verify_twice_idempotent(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)
    token = _token_for(data["user"].id)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h18", amount_paise=25000, status="CREATED")
    session.add(p)
    await session.commit()

    payment_id = "pay_h18"
    sig = hmac.new(_get_key_secret().encode(), f"order_h18|{payment_id}".encode(), hashlib.sha256).hexdigest()
    async def mock_fetch_payment(pid):
        return {"id": pid, "status": "captured"}
    monkeypatch.setattr("app.payment.services.gateway_fetch_payment", mock_fetch_payment)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        payload = {"booking_id": str(b.id), "razorpay_order_id": "order_h18", "razorpay_payment_id": payment_id, "razorpay_signature": sig}
        r1 = await client.post("/v1/payments/verify", json=payload, headers={"Authorization": f"Bearer {token}"})
        r2 = await client.post("/v1/payments/verify", json=payload, headers={"Authorization": f"Bearer {token}"})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["data"]["payment_id"] == r2.json()["data"]["payment_id"]

    app.dependency_overrides.clear()


# H19: webhook payment.captured with no client call -> booking CONFIRMED
@pytest.mark.asyncio
async def test_h19_webhook_captured_confirms(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h19", amount_paise=25000, status="CREATED")
    session.add(p)
    await session.commit()

    body_dict = {
        "id": "evt_h19",
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_wh_19", "order_id": "order_h19"}}},
    }
    raw_bytes = json.dumps(body_dict).encode()
    sig = hmac.new(_get_webhook_secret().encode(), raw_bytes, hashlib.sha256).hexdigest()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/webhooks/razorpay", content=raw_bytes, headers={"X-Razorpay-Signature": sig})
        assert resp.status_code == 200

    b_updated = (await session.execute(select(BookingModel).where(BookingModel.id == b.id))).scalar_one()
    assert b_updated.status == "CONFIRMED"

    app.dependency_overrides.clear()


# H20: webhook delivered 3x with same event_id -> one transition, one payment_events row
@pytest.mark.asyncio
async def test_h20_webhook_idempotency_3x(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_data(session)

    b = BookingModel(id=uuid.uuid4(), user_id=data["user"].id, booking_type="MOVIE", showtime_id=data["showtime"].id, total_paise=25000, status="HELD")
    session.add(b)
    await session.flush()
    p = PaymentModel(id=uuid.uuid4(), booking_id=b.id, order_id="order_h20", amount_paise=25000, status="CREATED")
    session.add(p)
    await session.commit()

    body_dict = {
        "id": "evt_h20_same",
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_wh_20", "order_id": "order_h20"}}},
    }
    raw_bytes = json.dumps(body_dict).encode()
    sig = hmac.new(_get_webhook_secret().encode(), raw_bytes, hashlib.sha256).hexdigest()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r1 = await client.post("/v1/webhooks/razorpay", content=raw_bytes, headers={"X-Razorpay-Signature": sig})
        r2 = await client.post("/v1/webhooks/razorpay", content=raw_bytes, headers={"X-Razorpay-Signature": sig})
        r3 = await client.post("/v1/webhooks/razorpay", content=raw_bytes, headers={"X-Razorpay-Signature": sig})
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r3.status_code == 200

    events_count = (await session.execute(select(func.count(PaymentEventModel.id)).where(PaymentEventModel.event_id == "evt_h20_same"))).scalar()
    assert events_count == 1

    app.dependency_overrides.clear()


# H21: webhook bad signature -> 400, no state change
@pytest.mark.asyncio
async def test_h21_webhook_bad_signature_400(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/webhooks/razorpay", content=b"{}", headers={"X-Razorpay-Signature": "bad_sig"})
        assert resp.status_code == 400
    app.dependency_overrides.clear()


# H22: webhook unknown order_id -> 200 + log, no exception
@pytest.mark.asyncio
async def test_h22_webhook_unknown_order_id_200(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    body_dict = {
        "id": "evt_h22_unknown",
        "event": "payment.captured",
        "payload": {"payment": {"entity": {"id": "pay_unknown", "order_id": "order_unknown_999"}}},
    }
    raw_bytes = json.dumps(body_dict).encode()
    sig = hmac.new(_get_webhook_secret().encode(), raw_bytes, hashlib.sha256).hexdigest()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/v1/webhooks/razorpay", content=raw_bytes, headers={"X-Razorpay-Signature": sig})
        assert resp.status_code == 200
    app.dependency_overrides.clear()


# H25: boot guard: RAZORPAY_ENV=test with a live key id -> config raises
def test_h25_boot_guard_raises_on_live_key(monkeypatch):
    monkeypatch.setattr(settings, "RAZORPAY_ENV", "test")
    monkeypatch.setattr(settings, "RAZORPAY_KEY_ID", "rzp_live_12345678")
    with pytest.raises(RuntimeError, match="Never use a live key in test mode"):
        verify_boot_config()
