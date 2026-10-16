import uuid
import pytest
from datetime import datetime, timedelta, timezone
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import jwt

from app.main import app
from app.core.config import settings
from app.core.database import get_db, Base
from app.auth.models import User as UserORM, UserRole
from app.movie.models import Venue, Screen, Showtime, Movie
from app.booking.models import BookingModel
from app.payment.models import PaymentModel
from app.admin.models import (
    TheatrePaymentConfigModel,
    CommissionLedgerModel,
)
from app.providers.registry import ProviderRegistryModel
from app.providers.base import ProviderTicket, ProviderTicketSeat
from app.booking.services import BookingService
from app.booking.repository import BookingRepository, TierCounterRepository
from app.shared.timeutil import utcnow


def _token_for(user_id: uuid.UUID, role: str = "SUPER_ADMIN") -> str:
    to_encode = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
        "type": "access",
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.mark.asyncio
async def test_pvr_commercial_configuration_and_model_b(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    # Create tables if needed
    async with session.bind.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    admin = UserORM(
        id=uuid.uuid4(),
        full_name="Finance Admin",
        email=f"fin_{uuid.uuid4().hex[:6]}@vyhbz.com",
        password_hash="hash",
        role=UserRole.FINANCE_ADMIN.value,
        is_active=True,
    )
    partner_id = uuid.uuid4()
    venue = Venue(
        id=uuid.uuid4(),
        name="PVR Cinemas Phoenix Marketcity",
        city="Bengaluru",
        address="Whitefield, Bengaluru",
        timezone="Asia/Kolkata",
        partner_id=partner_id,
    )
    session.add_all([admin, venue])
    await session.commit()

    token = _token_for(admin.id, role="FINANCE_ADMIN")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Update PVR configuration to Model B (VYHBZ_COLLECTS_SETTLES)
        put_res = await client.put(
            f"/v1/admin/theatres/{venue.id}/config",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "customer_payment_model": "VYHBZ_COLLECTS_SETTLES",
                "payment_provider": "RAZORPAY",
                "commission_model": "SETTLEMENT_DEDUCTION",
                "rate_type": "PERCENTAGE",
                "rate_value": 5.0,
                "reconciliation_source": "PVR_API",
                "contract_ref": "PVR-MSA-2026-OCT",
                "change_reason": "Configure PVR under Model B Vybhz Collects & Settles"
            }
        )
        assert put_res.status_code == 200, put_res.text
        put_data = put_res.json()["data"]
        assert put_data["customer_payment_model"] == "VYHBZ_COLLECTS_SETTLES"
        assert put_data["commission_model"] == "SETTLEMENT_DEDUCTION"
        assert put_data["payment_provider"] == "RAZORPAY"
        assert put_data["reconciliation_source"] == "PVR_API"

        # 2. Verify config persisted and returned via GET
        get_res = await client.get(
            f"/v1/admin/theatres/{venue.id}/config",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert get_res.status_code == 200
        get_data = get_res.json()["data"]
        assert get_data["customer_payment_model"] == "VYHBZ_COLLECTS_SETTLES"
        assert get_data["contract_ref"] == "PVR-MSA-2026-OCT"

        # 3. Verify in theatres listing
        list_res = await client.get("/v1/admin/theatres", headers={"Authorization": f"Bearer {token}"})
        assert list_res.status_code == 200
        theatres = list_res.json()["data"]["theatres"]
        pvr_theatre = next((t for t in theatres if t["id"] == str(venue.id)), None)
        assert pvr_theatre is not None
        assert pvr_theatre["customer_payment_model"] == "VYHBZ_COLLECTS_SETTLES"
        assert pvr_theatre["commission_model"] == "SETTLEMENT_DEDUCTION"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pvr_commit_records_commission_ledger(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session

    # 1. Seed venue, screen, movie, provider, showtime, user
    partner_id = uuid.uuid4()
    venue = Venue(
        id=uuid.uuid4(),
        name="PVR Grand Mall",
        city="Kochi",
        partner_id=partner_id,
    )
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Audi 1")
    movie = Movie(
        id=uuid.uuid4(),
        title="Oppenheimer",
        duration_min=180,
        language="English",
        certificate="A",
        status="PUBLISHED",
        partner_id=partner_id,
    )
    provider_reg = ProviderRegistryModel(
        id=uuid.uuid4(),
        name="PVR Test Provider",
        base_url="http://pvr-mock.local",
        auth_token_ref="secret_pvr_tok",
        hold_ttl_seconds=600,
        enabled=True,
    )
    session.add_all([venue, screen, movie, provider_reg])
    await session.flush()

    # Configure PVR venue with Model B
    pvr_cfg = TheatrePaymentConfigModel(
        venue_id=venue.id,
        customer_payment_model="VYHBZ_COLLECTS_SETTLES",
        payment_provider="RAZORPAY",
        commission_model="SETTLEMENT_DEDUCTION",
        rate_type="PERCENTAGE",
        rate_value=5.0000,
        calculation_base="GROSS_TICKET",
        reconciliation_source="PVR_API",
        effective_from=utcnow(),
        is_active=True
    )
    session.add(pvr_cfg)

    st = Showtime(
        id=uuid.uuid4(),
        screen_id=screen.id,
        movie_id=movie.id,
        starts_at=datetime.now(timezone.utc) + timedelta(days=1),
        partner_id=partner_id,
        provider_id=provider_reg.id,
        provider_showtime_ref="remote-st-pvr-101",
    )
    user = UserORM(
        id=uuid.uuid4(),
        full_name="Cinema Fan",
        email=f"pvr_fan_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="pwd",
        role="USER",
        is_active=True,
    )
    session.add_all([st, user])
    await session.commit()

    # 2. Seed a held booking with a verified payment
    booking_id = uuid.uuid4()
    b = BookingModel(
        id=booking_id,
        user_id=user.id,
        booking_type="MOVIE",
        showtime_id=st.id,
        provider_id=provider_reg.id,
        provider_hold_id="hold-pvr-99",
        held_until=datetime.now(timezone.utc) + timedelta(minutes=10),
        ticket_paise=40000,
        total_paise=40000,
        status="HELD",
        currency="INR",
        seat_codes_json='["A1", "A2"]',
        seat_refs_json='["s1", "s2"]',
        idempotency_key=f"idem-{uuid.uuid4().hex[:6]}",
    )
    pay = PaymentModel(
        id=uuid.uuid4(),
        booking_id=booking_id,
        order_id=f"order_{uuid.uuid4().hex[:8]}",
        payment_id=f"pay_{uuid.uuid4().hex[:8]}",
        amount_paise=40000,
        currency="INR",
        status="CAPTURED",
        signature_verified=True,
    )
    session.add_all([b, pay])
    await session.commit()

    # 3. Mock provider client to return a confirmed ticket
    class MockProvider:
        async def commit(self, hold_id: str, payment_ref: str | None = None) -> ProviderTicket:
            return ProviderTicket(
                booking_id="pvr-bk-777",
                ref_code="PVR-777",
                status="CONFIRMED",
                total_paise=40000,
                currency="INR",
                seats=[
                    ProviderTicketSeat(seat_ref="s1", seat_code="A1", price_paise=20000),
                    ProviderTicketSeat(seat_ref="s2", seat_code="A2", price_paise=20000)
                ],
                created_at=datetime.now(timezone.utc),
                barcode="BARCODE-777"
            )

    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: MockProvider()
    )

    # 4. Commit provider booking
    booking_repo = BookingRepository(session)
    tier_counter_repo = TierCounterRepository(session)
    service = BookingService(booking_repo, tier_counter_repo, session)

    confirmed_booking = await service.commit_booking(user_id=user.id, booking_id=booking_id, payment_ref="pay-razor-ref")
    assert confirmed_booking.status.value == "CONFIRMED"
    assert confirmed_booking.provider_booking_id == "pvr-bk-777"

    # 5. Verify CommissionLedgerModel record was created automatically
    ledger_stmt = select(CommissionLedgerModel).where(CommissionLedgerModel.booking_id == booking_id)
    ledger_res = await session.execute(ledger_stmt)
    entry = ledger_res.scalar_one_or_none()

    assert entry is not None
    assert entry.venue_id == venue.id
    assert entry.gross_ticket_paise == 40000
    assert entry.eligible_base_paise == 40000
    # 5% commission on 40,000 paise = 2,000 paise
    assert entry.commission_paise == 2000
    # 18% GST on 2,000 paise = 360 paise
    assert entry.tax_paise == 360
    assert entry.status == "UNINVOICED"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_pvr_reconciliation_detects_payment_success_booking_failure(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    admin = UserORM(
        id=uuid.uuid4(),
        full_name="Ops Admin",
        email=f"ops_{uuid.uuid4().hex[:6]}@vyhbz.com",
        password_hash="hash",
        role=UserRole.OPERATIONS_ADMIN.value,
        is_active=True,
    )
    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="PVR Orion", city="Bengaluru", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Screen 1")
    movie = Movie(
        id=uuid.uuid4(),
        title="Dune",
        duration_min=150,
        language="English",
        certificate="UA",
        status="PUBLISHED",
        partner_id=partner_id,
    )
    provider_reg = ProviderRegistryModel(id=uuid.uuid4(), name="PVR", base_url="http://pvr.test", enabled=True)
    session.add_all([admin, venue, screen, movie, provider_reg])
    await session.flush()

    st = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=utcnow(), provider_id=provider_reg.id, partner_id=partner_id)
    session.add(st)
    await session.flush()

    # Booking where customer paid but booking remained HELD (commit failed)
    bk_fail = BookingModel(
        id=uuid.uuid4(),
        user_id=admin.id,
        booking_type="MOVIE",
        showtime_id=st.id,
        provider_id=provider_reg.id,
        provider_hold_id="hold-stuck",
        held_until=utcnow() - timedelta(minutes=5),
        ticket_paise=50000,
        total_paise=50000,
        status="HELD", # Not CONFIRMED
        currency="INR"
    )
    pay_captured = PaymentModel(
        id=uuid.uuid4(),
        booking_id=bk_fail.id,
        order_id="order_captured_123",
        payment_id="pay_captured_123",
        amount_paise=50000,
        currency="INR",
        status="CAPTURED",
        signature_verified=True,
    )
    session.add_all([bk_fail, pay_captured])
    await session.commit()

    token = _token_for(admin.id, role="OPERATIONS_ADMIN")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Trigger reconciliation sync
        sync_res = await client.post("/v1/admin/reconciliation/sync", headers={"Authorization": f"Bearer {token}"})
        assert sync_res.status_code == 200, sync_res.text
        data = sync_res.json()["data"]
        assert data["new_exceptions_flagged"] >= 1

        # Check exceptions list
        exc_res = await client.get("/v1/admin/reconciliation/exceptions", headers={"Authorization": f"Bearer {token}"})
        assert exc_res.status_code == 200
        exceptions = exc_res.json()["data"]["exceptions"]
        flagged = next((e for e in exceptions if e["booking_id"] == str(bk_fail.id)), None)
        assert flagged is not None
        assert flagged["exception_type"] == "PAYMENT_SUCCESS_BOOKING_FAILURE"
        assert flagged["severity"] == "HIGH"
        assert flagged["external_ref"] == "pay_captured_123"

    app.dependency_overrides.clear()
