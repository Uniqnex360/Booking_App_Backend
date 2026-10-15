import uuid
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.core.database import get_db
from app.auth.models import User, UserRole, UsedPhoneEmailVerification
from app.auth.interfaces import User as AuthUserDomain
from app.auth.security import JWTTokenService
from app.user.models import UserProfileORM, AddressORM
from app.booking.models import BookingModel
from app.payment.models import PaymentModel


@pytest_asyncio.fixture
async def client(session):
    async def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_user_account_deletion_flow(session, client):
    user_id = uuid.uuid4()
    test_email = "delete_me@example.com"
    test_phone = "+919999988888"

    # 1. Seed user
    user = User(
        id=user_id,
        full_name="To Be Deleted",
        email=test_email,
        phone=test_phone,
        password_hash="mock_hash",
        role=UserRole.USER,
        is_verified=True,
        is_active=True,
    )
    session.add(user)

    # 2. Seed profile & address
    profile = UserProfileORM(
        id=uuid.uuid4(),
        user_id=user_id,
        bio="Hello world bio",
    )
    address = AddressORM(
        id=uuid.uuid4(),
        user_id=user_id,
        label="Home",
        line1="123 Test St",
        city="Test City",
        state="Test State",
        pincode="123456",
    )
    session.add(profile)
    session.add(address)

    # 3. Seed booking & payment with PII
    booking_id = uuid.uuid4()
    booking = BookingModel(
        id=booking_id,
        user_id=user_id,
        contact_email=test_email,
        contact_phone=test_phone,
        booking_type="EVENT",
        total_paise=150000,
        status="CONFIRMED",
        currency="INR",
    )
    session.add(booking)

    payment = PaymentModel(
        id=uuid.uuid4(),
        booking_id=booking_id,
        order_id=f"order_{uuid.uuid4().hex[:8]}",
        payment_id=f"pay_{uuid.uuid4().hex[:8]}",
        amount_paise=150000,
        currency="INR",
        status="SUCCESS",
        raw_event='{"customer_email": "delete_me@example.com", "contact": "+919999988888"}',
    )
    session.add(payment)

    # 4. Seed phone/email verification replay record
    verification_hash = "hash_token_abc_123"
    verification = UsedPhoneEmailVerification(
        id=uuid.uuid4(),
        url_hash=verification_hash,
        user_id=user_id,
    )
    session.add(verification)
    await session.commit()

    # Generate token
    user_domain = AuthUserDomain(
        id=user_id,
        full_name="To Be Deleted",
        email=test_email,
        phone=test_phone,
        password_hash="mock_hash",
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
    )
    token = JWTTokenService().create_access_token(user_domain)
    headers = {"Authorization": f"Bearer {token}"}

    # Delete account
    res = await client.delete("/v1/users/me", headers=headers)
    assert res.status_code == 200
    res_json = res.json()
    assert res_json["status"] == "success"
    assert "deleted" in res_json["message"].lower()

    # Verify user record is wiped
    user_res = await session.execute(select(User).where(User.id == user_id))
    assert user_res.scalar_one_or_none() is None

    # Verify profile & address are removed via cascade
    prof_res = await session.execute(
        select(UserProfileORM).where(UserProfileORM.user_id == user_id)
    )
    assert prof_res.scalar_one_or_none() is None

    addr_res = await session.execute(
        select(AddressORM).where(AddressORM.user_id == user_id)
    )
    assert addr_res.scalar_one_or_none() is None

    # Verify booking is kept for accounting but anonymized
    book_res = await session.execute(
        select(BookingModel).where(BookingModel.id == booking_id)
    )
    saved_booking = book_res.scalar_one_or_none()
    assert saved_booking is not None
    assert saved_booking.total_paise == 150000
    assert saved_booking.user_id is None
    assert saved_booking.contact_email is None
    assert saved_booking.contact_phone is None

    # Verify payment is kept for accounting but raw_event PII is scrubbed
    pay_res = await session.execute(
        select(PaymentModel).where(PaymentModel.booking_id == booking_id)
    )
    saved_payment = pay_res.scalar_one_or_none()
    assert saved_payment is not None
    assert saved_payment.amount_paise == 150000
    assert saved_payment.raw_event is None

    # Verify verification replay token is preserved, but user_id unlinked
    verif_res = await session.execute(
        select(UsedPhoneEmailVerification).where(
            UsedPhoneEmailVerification.url_hash == verification_hash
        )
    )
    saved_verif = verif_res.scalar_one_or_none()
    assert saved_verif is not None
    assert saved_verif.user_id is None

    # Verify re-signup with same email & phone succeeds without unique constraint clash
    new_user = User(
        id=uuid.uuid4(),
        full_name="New Person Same Email",
        email=test_email,
        phone=test_phone,
        password_hash="new_hash",
        role=UserRole.USER,
        is_verified=True,
        is_active=True,
    )
    session.add(new_user)
    await session.commit()
    re_query = await session.execute(select(User).where(User.email == test_email))
    assert re_query.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_user_account_deletion_old_token_gets_401(session, client):
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        full_name="Token Test User",
        email="tokentest@example.com",
        phone="+919876543200",
        password_hash="mock_hash",
        role=UserRole.USER,
        is_verified=True,
        is_active=True,
    )
    session.add(user)
    await session.commit()

    user_domain = AuthUserDomain(
        id=user_id,
        full_name="Token Test User",
        email="tokentest@example.com",
        phone="+919876543200",
        password_hash="mock_hash",
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
    )
    token = JWTTokenService().create_access_token(user_domain)
    headers = {"Authorization": f"Bearer {token}"}

    # Delete account
    del_res = await client.delete("/v1/users/me", headers=headers)
    assert del_res.status_code == 200

    # Old access token must now return 401 on any authenticated endpoint
    get_res = await client.get("/v1/users/me", headers=headers)
    assert get_res.status_code == 401

    # Second delete call with old token also gets 401
    second_del = await client.delete("/v1/users/me", headers=headers)
    assert second_del.status_code == 401


@pytest.mark.asyncio
async def test_admin_and_partner_deletion_blocked(session, client):
    # 1. Partner
    partner_id = uuid.uuid4()
    partner_user = User(
        id=partner_id,
        full_name="Partner User",
        email="partner@example.com",
        phone="+919876543201",
        password_hash="mock_hash",
        role=UserRole.PARTNER,
        is_verified=True,
        is_active=True,
    )
    session.add(partner_user)

    # 2. Admin
    admin_id = uuid.uuid4()
    admin_user = User(
        id=admin_id,
        full_name="Admin User",
        email="admin@example.com",
        phone="+919876543202",
        password_hash="mock_hash",
        role=UserRole.ADMIN,
        is_verified=True,
        is_active=True,
    )
    session.add(admin_user)
    await session.commit()

    # Attempt partner deletion
    partner_domain = AuthUserDomain(
        id=partner_id,
        full_name="Partner User",
        email="partner@example.com",
        phone="+919876543201",
        password_hash="mock_hash",
        role=UserRole.PARTNER,
        is_active=True,
        is_verified=True,
    )
    partner_token = JWTTokenService().create_access_token(partner_domain)
    res_p = await client.delete(
        "/v1/users/me", headers={"Authorization": f"Bearer {partner_token}"}
    )
    assert res_p.status_code == 403
    assert "support@vyhbz.com" in res_p.json()["detail"]

    # Verify partner user was NOT deleted
    p_check = await session.execute(select(User).where(User.id == partner_id))
    assert p_check.scalar_one_or_none() is not None

    # Attempt admin deletion
    admin_domain = AuthUserDomain(
        id=admin_id,
        full_name="Admin User",
        email="admin@example.com",
        phone="+919876543202",
        password_hash="mock_hash",
        role=UserRole.ADMIN,
        is_active=True,
        is_verified=True,
    )
    admin_token = JWTTokenService().create_access_token(admin_domain)
    res_a = await client.delete(
        "/v1/users/me", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_a.status_code == 403
    assert "support@vyhbz.com" in res_a.json()["detail"]

    # Verify admin user was NOT deleted
    a_check = await session.execute(select(User).where(User.id == admin_id))
    assert a_check.scalar_one_or_none() is not None
