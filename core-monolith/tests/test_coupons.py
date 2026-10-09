import uuid
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jwt

from app.main import app
from app.core.config import settings
from app.core.database import get_db
from app.auth.models import User as UserORM
from app.partner.models import PartnerORM
from app.event.models import EventORM, TicketCategoryORM
from app.coupon.models import CouponORM, CouponRedemptionORM
from app.booking.models import BookingModel
from app.payment.models import PaymentModel


def _token_for(user_id: uuid.UUID, role: str = "USER") -> str:
    to_encode = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def _create_partner_and_event(session: AsyncSession):
    partner_user = UserORM(
        id=uuid.uuid4(),
        full_name="Chef Partner",
        email=f"chef_{uuid.uuid4().hex[:6]}@restaurant.com",
        password_hash="hash",
        role="PARTNER",
        is_active=True,
    )
    session.add(partner_user)

    partner = PartnerORM(
        id=uuid.uuid4(),
        user_id=partner_user.id,
        business_name="Gourmet Dining Co",
        partner_type="restaurant",
        contact_name="Chef Partner",
        contact_phone="9988776655",
        city="Hyderabad",
        status="APPROVED",
    )
    session.add(partner)
    await session.commit()

    now = datetime.now(timezone.utc)
    event = EventORM(
        id=uuid.uuid4(),
        partner_id=partner.id,
        title="Royal Nizami Feast",
        slug=f"royal-nizami-feast-{uuid.uuid4().hex[:6]}",
        category="DINING",
        venue_name="Palace Hall",
        city="Hyderabad",
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=3),
        status="PUBLISHED",
    )
    session.add(event)

    tier = TicketCategoryORM(
        id=uuid.uuid4(),
        event_id=event.id,
        name="VIP Dining",
        price_paise=100000,  # ₹1,000
        capacity=50,
        is_active=True,
    )
    session.add(tier)
    await session.commit()
    return partner, partner_user, event, tier


@pytest.mark.asyncio
async def test_1_partner_creates_percent_coupon(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    partner, partner_user, event, _ = await _create_partner_and_event(session)
    partner_token = _token_for(partner_user.id, "PARTNER")

    now = datetime.now(timezone.utc)
    payload = {
        "code": "sunday20",
        "event_id": str(event.id),
        "discount_type": "PERCENT",
        "discount_value": 20,
        "min_order_paise": 100000,
        "max_discount_paise": 50000,
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
        "total_usage_limit": 100,
        "per_user_limit": 1,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/partner/coupons",
            json=payload,
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["code"] == "SUNDAY20"
        assert data["discount_type"] == "PERCENT"
        assert data["discount_value"] == 20
        assert data["min_order_paise"] == 100000
        assert data["max_discount_paise"] == 50000


@pytest.mark.asyncio
async def test_2_partner_creates_flat_coupon(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    partner, partner_user, _, _ = await _create_partner_and_event(session)
    partner_token = _token_for(partner_user.id, "PARTNER")

    now = datetime.now(timezone.utc)
    payload = {
        "code": "FLAT250",
        "event_id": None,  # Applies to all events
        "discount_type": "FLAT",
        "discount_value": 25000,  # ₹250
        "min_order_paise": 50000,
        "valid_from": (now - timedelta(days=1)).isoformat(),
        "valid_until": (now + timedelta(days=30)).isoformat(),
        "total_usage_limit": 50,
        "per_user_limit": 2,
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/partner/coupons",
            json=payload,
            headers={"Authorization": f"Bearer {partner_token}"},
        )
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["code"] == "FLAT250"
        assert data["discount_type"] == "FLAT"
        assert data["discount_value"] == 25000


@pytest.mark.asyncio
async def test_3_customer_applies_valid_coupon(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    partner, _, event, _ = await _create_partner_and_event(session)

    now = datetime.now(timezone.utc)
    coupon = CouponORM(
        code="FEAST20",
        partner_id=partner.id,
        event_id=event.id,
        discount_type="PERCENT",
        discount_value=20,
        min_order_paise=100000,  # ₹1,000
        max_discount_paise=50000,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=10),
        total_usage_limit=10,
        per_user_limit=1,
        is_active=True,
    )
    session.add(coupon)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/checkout/apply-coupon",
            json={"code": "feast20", "event_id": str(event.id), "cart_paise": 200000},  # ₹2,000
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert data["valid"] is True
        assert data["code"] == "FEAST20"
        assert data["discount_paise"] == 40000  # 20% of ₹2,000 = ₹400 = 40,000 paise
        assert data["final_paise"] == 160000


@pytest.mark.asyncio
async def test_4_customer_applies_below_min_order(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    partner, _, event, _ = await _create_partner_and_event(session)

    now = datetime.now(timezone.utc)
    coupon = CouponORM(
        code="MINORDERTEST",
        partner_id=partner.id,
        event_id=event.id,
        discount_type="FLAT",
        discount_value=10000,
        min_order_paise=150000,  # ₹1,500
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=10),
        is_active=True,
    )
    session.add(coupon)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/checkout/apply-coupon",
            json={"code": "MINORDERTEST", "event_id": str(event.id), "cart_paise": 100000},  # ₹1,000 < ₹1,500
        )
        assert res.status_code == 400
        body = res.json()
        assert "Minimum order" in (body.get("message") or body.get("detail", ""))


@pytest.mark.asyncio
async def test_5_customer_applies_expired_coupon(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    partner, _, event, _ = await _create_partner_and_event(session)

    now = datetime.now(timezone.utc)
    coupon = CouponORM(
        code="EXPIRED50",
        partner_id=partner.id,
        event_id=event.id,
        discount_type="PERCENT",
        discount_value=50,
        min_order_paise=0,
        valid_from=now - timedelta(days=10),
        valid_until=now - timedelta(days=1),  # Expired yesterday
        is_active=True,
    )
    session.add(coupon)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/checkout/apply-coupon",
            json={"code": "EXPIRED50", "event_id": str(event.id), "cart_paise": 100000},
        )
        assert res.status_code == 400
        body = res.json()
        assert "expired" in (body.get("message") or body.get("detail", "")).lower()


@pytest.mark.asyncio
async def test_6_customer_applies_event_scoped_coupon_to_wrong_event(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    partner, _, event, _ = await _create_partner_and_event(session)

    # Another event
    other_event = EventORM(
        id=uuid.uuid4(),
        partner_id=partner.id,
        title="Other Event",
        slug=f"other-event-{uuid.uuid4().hex[:6]}",
        category="DINING",
        venue_name="Other Hall",
        city="Hyderabad",
        starts_at=datetime.now(timezone.utc) + timedelta(days=3),
        ends_at=datetime.now(timezone.utc) + timedelta(days=3, hours=2),
        status="PUBLISHED",
    )
    session.add(other_event)

    now = datetime.now(timezone.utc)
    coupon = CouponORM(
        code="SPECIFIC10",
        partner_id=partner.id,
        event_id=event.id,  # Scoped specifically to event
        discount_type="PERCENT",
        discount_value=10,
        min_order_paise=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=10),
        is_active=True,
    )
    session.add(coupon)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/checkout/apply-coupon",
            json={"code": "SPECIFIC10", "event_id": str(other_event.id), "cart_paise": 100000},
        )
        assert res.status_code == 400
        body = res.json()
        assert "not valid for this event" in (body.get("message") or body.get("detail", "")).lower()


@pytest.mark.asyncio
async def test_7_total_usage_limit_enforced(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    partner, _, event, _ = await _create_partner_and_event(session)

    now = datetime.now(timezone.utc)
    coupon = CouponORM(
        code="LIMITEDONE",
        partner_id=partner.id,
        event_id=event.id,
        discount_type="FLAT",
        discount_value=10000,
        min_order_paise=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=10),
        total_usage_limit=1,
        used_count=1,  # Already used once
        is_active=True,
    )
    session.add(coupon)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/checkout/apply-coupon",
            json={"code": "LIMITEDONE", "event_id": str(event.id), "cart_paise": 100000},
        )
        assert res.status_code == 400
        body = res.json()
        assert "limit reached" in (body.get("message") or body.get("detail", "")).lower()


@pytest.mark.asyncio
async def test_8_per_user_limit_enforced(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    partner, _, event, _ = await _create_partner_and_event(session)

    user = UserORM(
        id=uuid.uuid4(),
        full_name="Repeat Customer",
        email=f"repeat_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="USER",
        is_active=True,
    )
    session.add(user)

    now = datetime.now(timezone.utc)
    coupon = CouponORM(
        code="ONCEONLY",
        partner_id=partner.id,
        event_id=event.id,
        discount_type="FLAT",
        discount_value=10000,
        min_order_paise=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=10),
        per_user_limit=1,
        is_active=True,
    )
    session.add(coupon)
    await session.commit()

    booking = BookingModel(
        id=uuid.uuid4(),
        user_id=user.id,
        quantity=1,
        total_paise=100000,
        currency="INR",
        status="CONFIRMED",
    )
    session.add(booking)
    await session.commit()

    # Record 1 existing redemption for this user
    redemption = CouponRedemptionORM(
        id=uuid.uuid4(),
        coupon_id=coupon.id,
        user_id=user.id,
        booking_id=booking.id,
        discount_paise=10000,
    )
    session.add(redemption)
    await session.commit()

    token = _token_for(user.id, "USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/checkout/apply-coupon",
            json={"code": "ONCEONLY", "event_id": str(event.id), "cart_paise": 100000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 400
        body = res.json()
        assert "already used" in (body.get("message") or body.get("detail", "")).lower()


@pytest.mark.asyncio
async def test_9_order_created_with_coupon_discounted_paise(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    partner, _, event, tier = await _create_partner_and_event(session)

    user = UserORM(
        id=uuid.uuid4(),
        full_name="Booking Customer",
        email=f"booker_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="USER",
        is_active=True,
    )
    session.add(user)

    now = datetime.now(timezone.utc)
    coupon = CouponORM(
        code="DINING30",
        partner_id=partner.id,
        event_id=event.id,
        discount_type="PERCENT",
        discount_value=30,  # 30% off ₹1,000 = ₹300 off -> ₹700
        min_order_paise=50000,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=10),
        is_active=True,
    )
    session.add(coupon)

    booking = BookingModel(
        id=uuid.uuid4(),
        user_id=user.id,
        tier_id=tier.id,
        quantity=1,
        total_paise=100000,  # ₹1,000
        currency="INR",
        status="HELD",
        held_until=now + timedelta(minutes=15),
    )
    session.add(booking)
    await session.commit()

    token = _token_for(user.id, "USER")
    mock_order = AsyncMock(return_value="order_test_coupon_123")
    monkeypatch.setattr(
        "app.payment.services.gateway_create_order",
        mock_order,
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/payments/order",
            json={"booking_id": str(booking.id), "coupon_code": "DINING30"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        # Total paise was 100,000. 30% discount is 30,000 paise. Net amount = 70,000 paise.
        assert data["amount_paise"] == 70000
        assert mock_order.called
        assert mock_order.call_args.kwargs["amount_paise"] == 70000


@pytest.mark.asyncio
async def test_10_payment_verified_records_redemption_and_increments_count(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    partner, _, event, tier = await _create_partner_and_event(session)

    user = UserORM(
        id=uuid.uuid4(),
        full_name="Verification Customer",
        email=f"verify_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="USER",
        is_active=True,
    )
    session.add(user)

    now = datetime.now(timezone.utc)
    coupon = CouponORM(
        id=uuid.uuid4(),
        code="FINAL100",
        partner_id=partner.id,
        event_id=event.id,
        discount_type="FLAT",
        discount_value=10000,  # ₹100 off
        min_order_paise=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=10),
        used_count=0,
        is_active=True,
    )
    session.add(coupon)

    booking = BookingModel(
        id=uuid.uuid4(),
        user_id=user.id,
        tier_id=tier.id,
        quantity=1,
        total_paise=100000,
        currency="INR",
        status="HELD",
        held_until=now + timedelta(minutes=15),
    )
    session.add(booking)

    import json
    payment = PaymentModel(
        id=uuid.uuid4(),
        booking_id=booking.id,
        order_id="order_verify_test",
        amount_paise=90000,
        currency="INR",
        status="CREATED",
        raw_event=json.dumps({
            "coupon_id": str(coupon.id),
            "coupon_code": "FINAL100",
            "discount_paise": 10000,
            "user_id": str(user.id),
        }),
    )
    session.add(payment)
    await session.commit()

    token = _token_for(user.id, "USER")

    monkeypatch.setattr("app.payment.services.gateway_verify_signature", lambda *a, **kw: True)
    monkeypatch.setattr(
        "app.payment.services.gateway_fetch_payment",
        AsyncMock(return_value={"id": "pay_test_999", "status": "captured"}),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            "/v1/payments/verify",
            json={
                "booking_id": str(booking.id),
                "razorpay_order_id": "order_verify_test",
                "razorpay_payment_id": "pay_test_999",
                "razorpay_signature": "valid_signature",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert res.status_code == 200

        # Verify redemption row in database
        redemption_res = await session.execute(
            select(CouponRedemptionORM).where(CouponRedemptionORM.coupon_id == coupon.id)
        )
        redemption = redemption_res.scalar_one_or_none()
        assert redemption is not None
        assert redemption.user_id == user.id
        assert redemption.booking_id == booking.id
        assert redemption.discount_paise == 10000

        # Verify used_count incremented
        updated_coupon_res = await session.execute(
            select(CouponORM).where(CouponORM.id == coupon.id)
        )
        updated_coupon = updated_coupon_res.scalar_one()
        assert updated_coupon.used_count == 1


@pytest.mark.asyncio
async def test_11_customer_lists_available_coupons_for_event(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    partner, _, event, _ = await _create_partner_and_event(session)

    now = datetime.now(timezone.utc)
    # 1. Active valid coupon for this event
    c1 = CouponORM(
        id=uuid.uuid4(),
        code="SHOWME20",
        partner_id=partner.id,
        event_id=event.id,
        discount_type="PERCENT",
        discount_value=20,
        min_order_paise=100000,
        max_discount_paise=50000,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=10),
        is_active=True,
    )
    # 2. Inactive coupon (should NOT be returned)
    c2 = CouponORM(
        id=uuid.uuid4(),
        code="HIDDEN50",
        partner_id=partner.id,
        event_id=event.id,
        discount_type="PERCENT",
        discount_value=50,
        min_order_paise=0,
        valid_from=now - timedelta(days=1),
        valid_until=now + timedelta(days=10),
        is_active=False,
    )
    session.add(c1)
    session.add(c2)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/v1/checkout/available-coupons?event_id={event.id}")
        assert res.status_code == 200
        coupons = res.json()["data"]
        codes = [c["code"] for c in coupons]
        assert "SHOWME20" in codes
        assert "HIDDEN50" not in codes
        item = next(c for c in coupons if c["code"] == "SHOWME20")
        assert "20% OFF up to ₹500" in item["discount_label"]
        assert "Min order ₹1,000" in item["min_order_label"]
