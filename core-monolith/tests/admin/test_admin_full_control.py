import uuid
import pytest
from datetime import datetime, timedelta
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
import jwt

from app.main import app
from app.core.config import settings
from app.core.database import get_db
from app.auth.models import User as UserORM
from app.movie.models import Movie as MovieORM, MovieStatus
from app.event.models import EventORM
from app.event.interfaces import EventCategory, EventStatus

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
async def test_admin_stats_and_overview(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    admin = UserORM(
        id=uuid.uuid4(),
        full_name="Super Admin",
        email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
    )
    session.add(admin)
    await session.commit()

    admin_token = _token_for(admin.id, role="ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get(
            "/v1/admin/stats",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert res.status_code == 200
        data = res.json()["data"]
        assert "users" in data
        assert "movies" in data
        assert "events" in data
        assert "partners" in data

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_admin_movies_control_show_and_hide(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    admin = UserORM(
        id=uuid.uuid4(),
        full_name="Admin Movie Mgr",
        email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
    )
    partner_id = uuid.uuid4()
    movie = MovieORM(
        id=uuid.uuid4(),
        title="Avatar: Fire & Ash",
        language="English",
        duration_min=180,
        certificate="UA",
        status=MovieStatus.PUBLISHED.value,
        partner_id=partner_id,
    )
    session.add_all([admin, movie])
    await session.commit()

    admin_token = _token_for(admin.id, role="ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Admin lists movies
        list_res = await client.get(
            "/v1/admin/movies?search=Avatar",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert list_res.status_code == 200
        movies = list_res.json()["data"]["movies"]
        assert any(m["id"] == str(movie.id) for m in movies)

        # 2. Admin hides movie by setting status to DRAFT
        hide_res = await client.patch(
            f"/v1/admin/movies/{movie.id}/status",
            json={"status": "DRAFT"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert hide_res.status_code == 200
        assert hide_res.json()["data"]["status"] == "DRAFT"

        # 3. Admin shows movie back by setting status to PUBLISHED
        show_res = await client.patch(
            f"/v1/admin/movies/{movie.id}/status",
            json={"status": "PUBLISHED"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert show_res.status_code == 200
        assert show_res.json()["data"]["status"] == "PUBLISHED"

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_admin_events_moderation_and_list(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    admin = UserORM(
        id=uuid.uuid4(),
        full_name="Admin Event Mgr",
        email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
    )
    partner_id = uuid.uuid4()
    from app.partner.models import PartnerORM
    partner = PartnerORM(
        id=partner_id,
        user_id=admin.id,
        business_name="Live Events Inc",
        partner_type="event_organiser",
        contact_name="Admin Partner",
        contact_phone="9876543210",
        city="Mumbai",
        status="APPROVED",
    )
    session.add_all([admin, partner])
    await session.commit()

    event = EventORM(
        id=uuid.uuid4(),
        partner_id=partner_id,
        title="Coldplay Live Mumbai",
        slug=f"coldplay-mumbai-{uuid.uuid4().hex[:6]}",
        category="concert",
        venue_name="DY Patil Stadium",
        city="Mumbai",
        starts_at=datetime.utcnow() + timedelta(days=10),
        ends_at=datetime.utcnow() + timedelta(days=10, hours=4),
        status="PENDING_APPROVAL",
    )
    session.add(event)
    await session.commit()



    admin_token = _token_for(admin.id, role="ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Admin lists events
        list_res = await client.get(
            "/v1/admin/events?search=Coldplay",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert list_res.status_code == 200
        events = list_res.json()["data"]["events"]
        assert any(e["id"] == str(event.id) for e in events)

        # 2. Admin approves event -> PUBLISHED
        approve_res = await client.patch(
            f"/v1/admin/events/{event.id}/status",
            json={"status": "PUBLISHED"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert approve_res.status_code == 200

        # 3. Admin rejects or delists event -> REJECTED with reason
        reject_res = await client.patch(
            f"/v1/admin/events/{event.id}/status",
            json={"status": "REJECTED", "cancellation_reason": "Missing organizer license"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert reject_res.status_code == 200

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_admin_users_list_and_block_unblock(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    admin = UserORM(
        id=uuid.uuid4(),
        full_name="Admin User Mgr",
        email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="ADMIN",
        is_active=True,
    )
    target_user = UserORM(
        id=uuid.uuid4(),
        full_name="Spam User",
        email=f"spammer_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="USER",
        is_active=True,
    )
    session.add_all([admin, target_user])
    await session.commit()

    admin_token = _token_for(admin.id, role="ADMIN")
    target_token = _token_for(target_user.id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Non-admin access to admin endpoint -> 403 Forbidden
        forbidden_res = await client.get(
            "/v1/admin/users",
            headers={"Authorization": f"Bearer {target_token}"},
        )
        assert forbidden_res.status_code == 403

        # 2. Admin searches and lists users
        users_res = await client.get(
            f"/v1/admin/users?search={target_user.email}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert users_res.status_code == 200
        user_list = users_res.json()["data"]["users"]
        assert any(u["id"] == str(target_user.id) for u in user_list)

        # 3. Admin blocks user
        block_res = await client.patch(
            f"/v1/admin/users/{target_user.id}/status",
            json={"is_active": False, "reason": "Terms violation"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert block_res.status_code == 200
        assert block_res.json()["data"]["is_active"] is False

        # 4. Admin unblocks user
        unblock_res = await client.patch(
            f"/v1/admin/users/{target_user.id}/status",
            json={"is_active": True},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert unblock_res.status_code == 200
        assert unblock_res.json()["data"]["is_active"] is True

        # 5. Admin self-block attempt is rejected
        self_block_res = await client.patch(
            f"/v1/admin/users/{admin.id}/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert self_block_res.status_code == 400

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_booking_rejected_when_movie_restricted_or_user_blocked(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    # 1. Setup Admin, User, Partner, Movie, Venue, Screen, Showtime, Seat
    from app.partner.models import PartnerORM
    admin = UserORM(id=uuid.uuid4(), full_name="Admin", email=f"adm_{uuid.uuid4().hex[:6]}@t.com", password_hash="h", role="ADMIN")
    user = UserORM(id=uuid.uuid4(), full_name="Customer", email=f"c_{uuid.uuid4().hex[:6]}@t.com", password_hash="h", role="USER", is_active=True)
    partner = PartnerORM(
        id=uuid.uuid4(), user_id=admin.id, business_name="Cinema Co",
        partner_type="event_organiser", contact_name="Admin",
        contact_phone="9999999999", city="Kochi", status="APPROVED",
    )
    session.add_all([admin, user, partner])
    await session.commit()

    from app.movie.models import Movie, Venue, Screen, ScreenRow, Seat, Showtime
    movie = Movie(
        id=uuid.uuid4(),
        title="Restricted Movie",
        partner_id=partner.id,
        status="DRAFT", # Admin restricted / not published
        language="English",
        certificate="UA",
        duration_min=120,
    )
    venue = Venue(id=uuid.uuid4(), name="Central Cinema", city="Kochi", partner_id=partner.id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Screen 1", total_seats=1)
    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", section="STALLS", seat_count=1, price_paise=20000)
    seat = Seat(id=uuid.uuid4(), row_id=row.id, number=1, code="A1", x=1)
    showtime = Showtime(
        id=uuid.uuid4(),
        movie_id=movie.id,
        screen_id=screen.id,
        partner_id=partner.id,
        starts_at=datetime.utcnow() + timedelta(days=2),
        status="ACTIVE",
    )
    session.add_all([movie, venue, screen, row, seat, showtime])
    await session.commit()

    user_token = _token_for(user.id, role="USER")
    admin_token = _token_for(admin.id, role="ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # A. Attempting to hold seats on a DRAFT/restricted movie is rejected with 409/400
        hold_res = await client.post(
            "/v1/bookings/seat-hold",
            json={"showtime_id": str(showtime.id), "seat_ids": [str(seat.id)]},
            headers={"Authorization": f"Bearer {user_token}", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert hold_res.status_code in (400, 409)
        assert "Movie is not available for booking" in hold_res.text

        # B. Admin publishes movie -> Hold now succeeds
        await client.patch(
            f"/v1/admin/movies/{movie.id}/status",
            json={"status": "PUBLISHED"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        hold_res2 = await client.post(
            "/v1/bookings/seat-hold",
            json={"showtime_id": str(showtime.id), "seat_ids": [str(seat.id)]},
            headers={"Authorization": f"Bearer {user_token}", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert hold_res2.status_code == 201

        # C. Admin blocks the user -> Any subsequent booking API call is rejected 401
        await client.patch(
            f"/v1/admin/users/{user.id}/status",
            json={"is_active": False},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        blocked_res = await client.post(
            "/v1/bookings/seat-hold",
            json={"showtime_id": str(showtime.id), "seat_ids": [str(seat.id)]},
            headers={"Authorization": f"Bearer {user_token}", "Idempotency-Key": str(uuid.uuid4())},
        )
        assert blocked_res.status_code == 401

    app.dependency_overrides.clear()

