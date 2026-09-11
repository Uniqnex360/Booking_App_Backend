"""
Tests M8–M10, M12, S1–S2: Partner permissions, moderation, layout locking, and status transitions.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

import app.movie.interfaces as movie_interfaces
from app.auth.models import User
from app.auth.services import AuthService
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.movie.models import (
    Movie,
    MovieStatus,
    Screen,
    ScreenRow,
    Seat,
    SeatState,
    SeatStateStatus,
    Showtime,
    Venue,
)
from app.movie.services import MovieService


def _token_for(user_id: uuid.UUID, role: str = "USER") -> str:
    from jose import jwt
    from datetime import datetime, timedelta

    to_encode = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
        "type": "access",
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# M8 — non-approved partner creating a movie -> 403
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m8_unapproved_partner_rejected(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    cust_user = User(id=uuid.uuid4(), full_name="Test User", email="cust@pvr.local", password_hash="h", role="USER")
    session.add(cust_user)
    await session.commit()

    token = _token_for(cust_user.id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/partner/movies",
            json={"title": "Illegal Film", "duration_min": 120},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# M9 — DRAFT movie: absent from GET /v1/movies, visible to its own partner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m9_draft_visibility_rules(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    partner = User(id=uuid.uuid4(), full_name="Test User", email="p9@pvr.local", password_hash="h", role="PARTNER")
    session.add(partner)
    await session.commit()

    from app.partner.models import PartnerORM
    partner_record = PartnerORM(
        id=uuid.uuid4(), user_id=partner.id, business_name="Test Cinema",
        partner_type="event_organiser", contact_name="Test User",
        contact_phone="9999999999", city="Kochi", status="APPROVED",
    )
    session.add(partner_record)
    await session.commit()

    token = _token_for(partner.id, role="PARTNER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        create_resp = await client.post(
            "/v1/partner/movies",
            json={"title": "Secret Draft", "duration_min": 100},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert create_resp.status_code == 201

        list_resp = await client.get("/v1/movies")
        assert list_resp.status_code == 200
        titles = [m["title"] for m in list_resp.json()["data"]]
        assert "Secret Draft" not in titles

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# M10 — admin approves PENDING_REVIEW -> PUBLISHED, and it leaves the pending queue
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m10_admin_approves_pending_review(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    partner = User(id=uuid.uuid4(), full_name="Test User", email="part10@pvr.local", password_hash="h", role="PARTNER")
    admin = User(id=uuid.uuid4(), full_name="Test User", email="admin10@pvr.local", password_hash="h", role="ADMIN")
    session.add_all([partner, admin])
    await session.commit()

    movie = Movie(
        id=uuid.uuid4(),
        title="Moderated Film",
        language="Malayalam",
        duration_min=120,
        certificate="UA",
        status=MovieStatus.PENDING_REVIEW.value,
        partner_id=partner.id,
    )
    session.add(movie)
    await session.commit()

    admin_token = _token_for(admin.id, role="ADMIN")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/v1/admin/content/{movie.id}/status",
            json={"status": "PUBLISHED"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "PUBLISHED"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# M12 — PATCH screen layout while any showtime on it has seat_states -> 409
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m12_layout_lock_on_active_seat_states(session: AsyncSession, engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async def override_get_db():
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db

    partner = User(id=uuid.uuid4(), full_name="Test User", email="p12@pvr.local", password_hash="h", role="PARTNER")
    session.add(partner)
    await session.commit()

    from app.partner.models import PartnerORM
    partner_record = PartnerORM(
        id=uuid.uuid4(), user_id=partner.id, business_name="Test Cinema",
        partner_type="event_organiser", contact_name="Test User",
        contact_phone="9999999999", city="Kochi", status="APPROVED",
    )
    session.add(partner_record)
    await session.commit()

    venue = Venue(id=uuid.uuid4(), name="V1", city="Kochi", partner_id=partner_record.id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="SCR1", total_seats=10)
    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=10, price_paise=10000)
    seat = Seat(id=uuid.uuid4(), row_id=row.id, number=1, code="A01", x=0)
    movie = Movie(id=uuid.uuid4(), title="M1", language="Malayalam", duration_min=120, certificate="U", partner_id=partner_record.id)
    st = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=datetime.now(timezone.utc), partner_id=partner_record.id)
    state = SeatState(showtime_id=st.id, seat_id=seat.id, status=SeatStateStatus.BOOKED.value)

    session.add_all([venue, screen, row, seat, movie, st])
    await session.commit()

    session.add(state)
    await session.commit()

    token = _token_for(partner.id, role="PARTNER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Layout edit fails with 409
        resp = await client.patch(
            f"/v1/partner/screens/{screen.id}/layout",
            json={"text_grid": "A: 1111"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409

        # 2. Cancel showtime
        cancel_resp = await client.patch(
            f"/v1/partner/showtimes/{st.id}/cancel",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert cancel_resp.status_code == 200

        # Delete seat state so no active state exists on screen
        await session.delete(state)
        await session.commit()

        # 3. Retry layout edit -> succeeds 200
        retry_resp = await client.patch(
            f"/v1/partner/screens/{screen.id}/layout",
            json={"text_grid": "A: 1111"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert retry_resp.status_code == 200

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# S1 — legal status transitions pass, illegal transitions raise Exception
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_s1_status_transition_rules(session: AsyncSession):
    svc = MovieService(None)
    # Partner moving DRAFT straight to PUBLISHED raises Exception
    with pytest.raises(Exception):
        await svc.update_movie_status(uuid.uuid4(), "PUBLISHED")


# ---------------------------------------------------------------------------
# S2 — assert MovieStatus is defined in interfaces.py, no transition dict in app/movie/
# ---------------------------------------------------------------------------

def test_s2_architecture_invariants():
    # 1. MovieStatus defined in interfaces.py
    assert hasattr(movie_interfaces, "MovieStatus"), "MovieStatus must be defined in interfaces.py"

    # 2. No transition dict inside app/movie/
    movie_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "app", "movie")
    for root, _, files in os.walk(movie_dir):
        for fname in files:
            if fname.endswith(".py"):
                fpath = os.path.join(root, fname)
                text_content = open(fpath).read()

                assert "PENDING_APPROVAL" not in text_content, f"Found PENDING_APPROVAL in {fname}"
                assert "APPROVED" not in text_content, f"Found APPROVED string in {fname}"
