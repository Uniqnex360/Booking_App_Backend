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
from app.partner.models import PartnerORM
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


@pytest.mark.asyncio
async def test_ops_admin_endpoint_authorization(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    venue = Venue(
        id=uuid.uuid4(),
        name="Test Ops Venue",
        city="Bengaluru",
        address="Koramangala",
        timezone="Asia/Kolkata"
    )
    session.add(venue)
    await session.flush()

    screen = Screen(
        id=uuid.uuid4(),
        venue_id=venue.id,
        name="Screen 1",
        total_seats=0
    )
    session.add(screen)

    roles = ["SUPER_ADMIN", "OPERATIONS_ADMIN", "FINANCE_ADMIN", "SUPPORT_ADMIN"]
    tokens = {}
    for r in roles:
        u = UserORM(
            id=uuid.uuid4(),
            full_name=f"{r} User",
            email=f"{r.lower()}_{uuid.uuid4().hex[:6]}@vyhbz.com",
            password_hash="hash",
            role=r,
            is_active=True,
        )
        session.add(u)
        tokens[r] = _token_for(u.id, role=r)

    partner_owner = UserORM(
        id=uuid.uuid4(),
        full_name="Partner Owner",
        email=f"owner_{uuid.uuid4().hex[:6]}@partner.com",
        password_hash="hash",
        role="PARTNER",
        is_active=True,
    )
    session.add(partner_owner)
    await session.flush()

    partner = PartnerORM(
        id=uuid.uuid4(),
        user_id=partner_owner.id,
        business_name="Test Partner Ops",
        partner_type="cinema",
        contact_name="Owner Name",
        contact_phone="9988776655",
        city="Bengaluru",
        status="PENDING_APPROVAL"
    )
    session.add(partner)

    await session.commit()

    layout_payload = {
        "text_grid": "A: 1111",
        "default_price_paise": 20000,
        "override_reason": "Ops layout verification"
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test 1: POST /v1/admin/screens/{id}/layout
        for role in roles:
            res = await client.post(
                f"/v1/admin/screens/{screen.id}/layout",
                headers={"Authorization": f"Bearer {tokens[role]}"},
                json=layout_payload,
            )
            expected = 200 if role in ("SUPER_ADMIN", "OPERATIONS_ADMIN") else 403
            assert res.status_code == expected, f"Role {role} got {res.status_code}, expected {expected} on screen layout"

        # Test 2: GET /v1/partner/admin
        for role in roles:
            res = await client.get(
                "/v1/partner/admin",
                headers={"Authorization": f"Bearer {tokens[role]}"},
            )
            expected = 200 if role in ("SUPER_ADMIN", "OPERATIONS_ADMIN") else 403
            assert res.status_code == expected, f"Role {role} got {res.status_code}, expected {expected} on partner listing"

        # Test 3: PATCH /v1/admin/partners/{id}/status
        for role in roles:
            p_owner = UserORM(
                id=uuid.uuid4(),
                full_name=f"Partner Owner {role}",
                email=f"owner_{role.lower()}_{uuid.uuid4().hex[:6]}@partner.com",
                password_hash="hash",
                role="PARTNER",
                is_active=True,
            )
            session.add(p_owner)
            await session.flush()
            p_inst = PartnerORM(
                id=uuid.uuid4(),
                user_id=p_owner.id,
                business_name=f"Partner {role}",
                partner_type="cinema",
                contact_name="Owner",
                contact_phone="9988776655",
                city="Bengaluru",
                status="PENDING_APPROVAL"
            )
            session.add(p_inst)
            await session.commit()

            res = await client.patch(
                f"/v1/admin/partners/{p_inst.id}/status",
                headers={"Authorization": f"Bearer {tokens[role]}"},
                json={"status": "APPROVED"},
            )
            expected = 200 if role in ("SUPER_ADMIN", "OPERATIONS_ADMIN") else 403
            assert res.status_code == expected, f"Role {role} got {res.status_code}, expected {expected} on partner status update"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_super_admin_user_role_status_guards(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    # 1. Create caller users for all admin roles
    all_roles = ["SUPER_ADMIN", "ADMIN", "OPERATIONS_ADMIN", "FINANCE_ADMIN", "SUPPORT_ADMIN"]
    users = {}
    tokens = {}
    for r in all_roles:
        u = UserORM(
            id=uuid.uuid4(),
            full_name=f"{r} Caller",
            email=f"{r.lower()}_{uuid.uuid4().hex[:6]}@portal.com",
            password_hash="hash",
            role=r,
            is_active=True,
        )
        session.add(u)
        users[r] = u
        tokens[r] = _token_for(u.id, role=r)

    # 2. Target regular user
    regular_user = UserORM(
        id=uuid.uuid4(),
        full_name="Regular User",
        email=f"regular_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="hash",
        role="USER",
        is_active=True,
    )
    session.add(regular_user)

    # 3. Target admin user (for target privilege protection check)
    target_admin = UserORM(
        id=uuid.uuid4(),
        full_name="Target Admin",
        email=f"target_admin_{uuid.uuid4().hex[:6]}@portal.com",
        password_hash="hash",
        role="OPERATIONS_ADMIN",
        is_active=True,
    )
    session.add(target_admin)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Check 1: SUPER_ADMIN and ADMIN get 200; OPERATIONS, FINANCE, SUPPORT get 403
        for r in all_roles:
            status_res = await client.patch(
                f"/v1/admin/users/{regular_user.id}/status",
                headers={"Authorization": f"Bearer {tokens[r]}"},
                json={"is_active": True},
            )
            role_res = await client.patch(
                f"/v1/admin/users/{regular_user.id}/role",
                headers={"Authorization": f"Bearer {tokens[r]}"},
                json={"role": "USER"},
            )
            expected = 200 if r in ("SUPER_ADMIN", "ADMIN") else 403
            assert status_res.status_code == expected, f"{r} got {status_res.status_code} on status update, expected {expected}"
            assert role_res.status_code == expected, f"{r} got {role_res.status_code} on role update, expected {expected}"

        # Check 2: ADMIN -> SUPER_ADMIN target = 403, SUPER_ADMIN -> same = 200
        another_super_admin = UserORM(
            id=uuid.uuid4(),
            full_name="Another Super Admin",
            email=f"another_super_{uuid.uuid4().hex[:6]}@portal.com",
            password_hash="hash",
            role="SUPER_ADMIN",
            is_active=True,
        )
        session.add(another_super_admin)
        await session.commit()

        # ADMIN modifying SUPER_ADMIN target -> 403 ForbiddenError
        admin_modify_super_status = await client.patch(
            f"/v1/admin/users/{another_super_admin.id}/status",
            headers={"Authorization": f"Bearer {tokens['ADMIN']}"},
            json={"is_active": True},
        )
        assert admin_modify_super_status.status_code == 403, "ADMIN cannot modify SUPER_ADMIN target status"

        admin_modify_super_role = await client.patch(
            f"/v1/admin/users/{another_super_admin.id}/role",
            headers={"Authorization": f"Bearer {tokens['ADMIN']}"},
            json={"role": "USER"},
        )
        assert admin_modify_super_role.status_code == 403, "ADMIN cannot modify SUPER_ADMIN target role"

        # ADMIN granting SUPER_ADMIN role -> 403 ForbiddenError
        admin_grant_super = await client.patch(
            f"/v1/admin/users/{regular_user.id}/role",
            headers={"Authorization": f"Bearer {tokens['ADMIN']}"},
            json={"role": "SUPER_ADMIN"},
        )
        assert admin_grant_super.status_code == 403, "ADMIN cannot grant SUPER_ADMIN role"

        # SUPER_ADMIN modifying SUPER_ADMIN target -> 200 OK
        super_modify_super_status = await client.patch(
            f"/v1/admin/users/{another_super_admin.id}/status",
            headers={"Authorization": f"Bearer {tokens['SUPER_ADMIN']}"},
            json={"is_active": True},
        )
        assert super_modify_super_status.status_code == 200, "SUPER_ADMIN can modify SUPER_ADMIN target status"

        # Check 3: Self-block rejected (400)
        self_block_res = await client.patch(
            f"/v1/admin/users/{users['SUPER_ADMIN'].id}/status",
            headers={"Authorization": f"Bearer {tokens['SUPER_ADMIN']}"},
            json={"is_active": False},
        )
        assert self_block_res.status_code == 400
        assert "cannot block their own account" in self_block_res.json()["detail"]

        # Check 4: Self-demote rejected (400)
        # SUPER_ADMIN attempting self-demote to ADMIN or USER
        self_demote_res = await client.patch(
            f"/v1/admin/users/{users['SUPER_ADMIN'].id}/role",
            headers={"Authorization": f"Bearer {tokens['SUPER_ADMIN']}"},
            json={"role": "USER"},
        )
        assert self_demote_res.status_code == 400
        assert "cannot demote their own account" in self_demote_res.json()["detail"]

        self_demote_admin_res = await client.patch(
            f"/v1/admin/users/{users['SUPER_ADMIN'].id}/role",
            headers={"Authorization": f"Bearer {tokens['SUPER_ADMIN']}"},
            json={"role": "ADMIN"},
        )
        assert self_demote_admin_res.status_code == 400
        assert "cannot demote their own account" in self_demote_admin_res.json()["detail"]

        # ADMIN attempting self-demote to USER
        admin_self_demote = await client.patch(
            f"/v1/admin/users/{users['ADMIN'].id}/role",
            headers={"Authorization": f"Bearer {tokens['ADMIN']}"},
            json={"role": "USER"},
        )
        assert admin_self_demote.status_code == 400
        assert "cannot demote their own account" in admin_self_demote.json()["detail"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_stats_and_integrations_health_smoke(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    admin_user = UserORM(
        id=uuid.uuid4(),
        full_name="Admin Smoke Tester",
        email=f"smoke_{uuid.uuid4().hex[:6]}@portal.com",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
    )
    session.add(admin_user)
    await session.commit()
    token = _token_for(admin_user.id, role="ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        stats_res = await client.get(
            "/v1/admin/stats/comprehensive",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert stats_res.status_code == 200, f"Expected 200, got {stats_res.status_code}: {stats_res.text}"
        data = stats_res.json()["data"]
        assert "total_bookings" in data
        assert "commission_earned_paise" in data

        health_res = await client.get(
            "/v1/admin/integrations/health",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert health_res.status_code == 200, f"Expected 200, got {health_res.status_code}: {health_res.text}"
        integrations = health_res.json()["data"]
        assert isinstance(integrations, list)
        assert len(integrations) > 0
        assert "latency_ms" in integrations[0]

    app.dependency_overrides.clear()



