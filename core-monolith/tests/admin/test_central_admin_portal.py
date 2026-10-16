import uuid
import pytest
from datetime import datetime, timedelta
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from app.main import app
from app.core.config import settings
from app.core.database import get_db, Base
from app.auth.models import User as UserORM, UserRole
from app.movie.models import Venue, Screen, Showtime, Movie
from app.booking.models import BookingModel
from app.admin.models import (
    TheatreChainModel,
    TheatrePaymentConfigModel,
    CommissionLedgerModel,
    CommissionInvoiceModel,
    ReconciliationExceptionModel
)
from app.shared.timeutil import utcnow


def _token_for(user_id: uuid.UUID, role: str = "ADMIN") -> str:
    to_encode = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
        "type": "access",
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


@pytest.mark.asyncio
async def test_theatre_chains_and_listing(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    # Create tables if needed in test db
    async with session.bind.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    admin = UserORM(
        id=uuid.uuid4(),
        full_name="Operations Admin",
        email=f"ops_{uuid.uuid4().hex[:6]}@vyhbz.com",
        password_hash="hash",
        role=UserRole.OPERATIONS_ADMIN.value,
        is_active=True,
    )
    session.add(admin)

    # Seed a venue
    venue = Venue(
        id=uuid.uuid4(),
        name="PVR Grand Galada",
        city="Chennai",
        address="Pallavaram, Chennai",
        timezone="Asia/Kolkata"
    )
    session.add(venue)
    await session.commit()

    token = _token_for(admin.id, role="OPERATIONS_ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create a chain
        chain_res = await client.post(
            "/v1/admin/chains",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "name": "PVR Inox",
                "code": f"PVR_{uuid.uuid4().hex[:4].upper()}",
                "contact_email": "partnerships@pvr.com",
                "contact_phone": "+919876543210",
                "notes": "National multiplex partner"
            }
        )
        assert chain_res.status_code == 200, chain_res.text
        chain_data = chain_res.json()["data"]
        assert chain_data["name"] == "PVR Inox"

        # 2. List chains
        list_chains = await client.get(
            "/v1/admin/chains",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert list_chains.status_code == 200
        assert len(list_chains.json()["data"]) >= 1

        # 3. List theatres
        theatres_res = await client.get(
            "/v1/admin/theatres",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert theatres_res.status_code == 200
        data = theatres_res.json()["data"]
        assert data["total"] >= 1
        theatre_item = next(t for t in data["theatres"] if str(t["id"]) == str(venue.id))
        assert theatre_item["name"] == "PVR Grand Galada"
        assert theatre_item["customer_payment_model"] == "THEATRE_DIRECT"
        assert theatre_item["commission_model"] == "INVOICE_POST_PAY"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_per_theatre_config_and_history(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    finance_admin = UserORM(
        id=uuid.uuid4(),
        full_name="Finance Director",
        email=f"finance_{uuid.uuid4().hex[:6]}@vyhbz.com",
        password_hash="hash",
        role=UserRole.FINANCE_ADMIN.value,
        is_active=True,
    )
    session.add(finance_admin)

    venue = Venue(
        id=uuid.uuid4(),
        name="AGS Cinemas T Nagar",
        city="Chennai",
        address="T Nagar, Chennai",
        timezone="Asia/Kolkata"
    )
    session.add(venue)
    await session.commit()

    token = _token_for(finance_admin.id, role="FINANCE_ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Fetch default configuration
        cfg_res = await client.get(
            f"/v1/admin/theatres/{venue.id}/config",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert cfg_res.status_code == 200
        cfg = cfg_res.json()["data"]
        assert cfg["customer_payment_model"] == "THEATRE_DIRECT"
        assert cfg["commission_model"] == "INVOICE_POST_PAY"
        assert cfg["invoice_cycle"] == "WEEKLY"
        assert cfg["due_days"] == 15
        assert float(cfg["rate_value"]) == 5.0

        # 2. Update configuration
        update_res = await client.put(
            f"/v1/admin/theatres/{venue.id}/config",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "customer_payment_model": "THEATRE_DIRECT",
                "commission_model": "INVOICE_POST_PAY",
                "rate_type": "PERCENTAGE",
                "rate_value": 7.5,
                "calculation_base": "GROSS_TICKET",
                "invoice_cycle": "WEEKLY",
                "due_days": 21,
                "contract_ref": "AGS-2026-REV",
                "change_reason": "Annual commission renegotiation"
            }
        )
        assert update_res.status_code == 200
        updated = update_res.json()["data"]
        assert float(updated["rate_value"]) == 7.5
        assert updated["due_days"] == 21
        assert updated["contract_ref"] == "AGS-2026-REV"

        # 3. Check audit history
        hist_res = await client.get(
            f"/v1/admin/theatres/{venue.id}/config/history",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert hist_res.status_code == 200
        history = hist_res.json()["data"]
        assert len(history) >= 1
        assert history[0]["change_reason"] == "Annual commission renegotiation"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_commission_ledger_and_invoicing_flow(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    admin = UserORM(
        id=uuid.uuid4(),
        full_name="Super Admin",
        email=f"admin_{uuid.uuid4().hex[:6]}@vyhbz.com",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
    )
    session.add(admin)

    venue = Venue(
        id=uuid.uuid4(),
        name="PVR VR Mall",
        city="Chennai",
        address="Anna Nagar, Chennai",
        timezone="Asia/Kolkata"
    )
    session.add(venue)

    # Seed booking and commission ledger
    booking = BookingModel(
        id=uuid.uuid4(),
        ref_code="AGS-TESTLEDGER",
        booking_type="MOVIE",
        total_paise=100000, # 1000 INR
        ticket_paise=90000,
        convenience_fee_paise=10000,
        status="CONFIRMED",
        created_at=utcnow()
    )
    session.add(booking)
    await session.flush()

    ledger_entry = CommissionLedgerModel(
        id=uuid.uuid4(),
        booking_id=booking.id,
        venue_id=venue.id,
        gross_ticket_paise=90000,
        eligible_base_paise=90000,
        rate_type="PERCENTAGE",
        rate_value=5.0,
        commission_paise=4500, # 5% of 900 INR = 45 INR
        tax_paise=810, # 18% GST = 8.10 INR
        status="UNINVOICED",
        created_at=utcnow() - timedelta(days=2)
    )
    session.add(ledger_entry)
    await session.commit()

    token = _token_for(admin.id, role="ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. List commission ledger
        led_res = await client.get(
            f"/v1/admin/commission/ledger?venue_id={venue.id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert led_res.status_code == 200
        entries = led_res.json()["data"]["entries"]
        assert len(entries) >= 1
        assert entries[0]["commission_paise"] == 4500

        # 2. Generate invoice
        now = utcnow()
        inv_res = await client.post(
            "/v1/admin/commission/invoices/generate",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "venue_id": str(venue.id),
                "period_start": (now - timedelta(days=7)).isoformat(),
                "period_end": now.isoformat(),
                "due_days": 15,
                "notes": "Weekly invoice run"
            }
        )
        assert inv_res.status_code == 200, inv_res.text
        inv_data = inv_res.json()["data"]
        invoice_id = inv_data["id"]
        assert inv_data["commission_paise"] == 4500
        assert inv_data["total_paise"] == 4500 + 810
        assert inv_data["status"] == "DRAFT"

        # 3. Transition invoice to ISSUED
        issue_res = await client.patch(
            f"/v1/admin/commission/invoices/{invoice_id}/status",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "ISSUED", "notes": "Approved for dispatch"}
        )
        assert issue_res.status_code == 200
        assert issue_res.json()["data"]["status"] == "ISSUED"

        # 4. Record collection payment
        pay_res = await client.post(
            f"/v1/admin/commission/invoices/{invoice_id}/collections",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "amount_paise": inv_data["total_paise"],
                "payment_method": "NEFT",
                "payment_ref": "NEFT123456789",
                "notes": "Settled in full"
            }
        )
        assert pay_res.status_code == 200

        # 5. Verify invoice status is now PAID
        check_res = await client.get(
            f"/v1/admin/commission/invoices?venue_id={venue.id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert check_res.status_code == 200
        invs = check_res.json()["data"]["invoices"]
        matched = next(i for i in invs if i["id"] == invoice_id)
        assert matched["status"] == "PAID"
        assert matched["balance_paise"] == 0

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_reconciliation_exceptions_lifecycle(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    admin = UserORM(
        id=uuid.uuid4(),
        full_name="Operations Specialist",
        email=f"ops_{uuid.uuid4().hex[:6]}@vyhbz.com",
        password_hash="hash",
        role="OPERATIONS_ADMIN",
        is_active=True,
    )
    session.add(admin)
    await session.commit()

    token = _token_for(admin.id, role="OPERATIONS_ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Seed an exception
        from app.admin.reconciliation_service import ReconciliationAdminService
        exc = await ReconciliationAdminService.flag_exception(
            session,
            exception_type="BOOKING_PAYMENT_MISMATCH",
            discrepancy_details="Payment captured in Razorpay but partner webhook timed out",
            severity="HIGH"
        )

        # 1. List exceptions
        list_res = await client.get(
            "/v1/admin/reconciliation/exceptions",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert list_res.status_code == 200
        excs = list_res.json()["data"]["exceptions"]
        assert len(excs) >= 1

        # 2. Resolve exception
        resolve_res = await client.patch(
            f"/v1/admin/reconciliation/exceptions/{exc.id}/resolve",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "status": "RESOLVED",
                "resolution_notes": "Confirmed seats manually with theatre manager and regenerated ticket barcode"
            }
        )
        assert resolve_res.status_code == 200
        resolved = resolve_res.json()["data"]
        assert resolved["status"] == "RESOLVED"
        assert "theatre manager" in resolved["resolution_notes"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rbac_security_restriction(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    support_user = UserORM(
        id=uuid.uuid4(),
        full_name="Support Agent",
        email=f"support_{uuid.uuid4().hex[:6]}@vyhbz.com",
        password_hash="hash",
        role="SUPPORT_ADMIN",
        is_active=True,
    )
    session.add(support_user)
    await session.commit()

    support_token = _token_for(support_user.id, role="SUPPORT_ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Support Admin CAN search bookings
        search_res = await client.get(
            "/v1/admin/bookings/detailed-search",
            headers={"Authorization": f"Bearer {support_token}"}
        )
        assert search_res.status_code == 200

        # Support Admin CANNOT modify financial terms (requires Finance Admin)
        fake_id = uuid.uuid4()
        config_res = await client.put(
            f"/v1/admin/theatres/{fake_id}/config",
            headers={"Authorization": f"Bearer {support_token}"},
            json={"rate_value": 10.0}
        )
        assert config_res.status_code == 403, "Support admin must be forbidden from updating financial terms"

    app.dependency_overrides.clear()
