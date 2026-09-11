"""
Tests M1–M7: Movie catalog, database constraints, seat lifecycle, and concurrency.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime, timezone

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
# M1 — 10 rows x 24 -> COUNT(seats) == 240, codes A01..J24, no duplicate (row_id, code)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m1_catalog_generation_and_uniqueness(session: AsyncSession):
    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="PVR Lulu Mall", city="Kochi", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Screen 1", total_seats=240)
    session.add_all([venue, screen])
    await session.flush()

    row_labels = ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"]
    all_seats = []
    for label in row_labels:
        row = ScreenRow(
            id=uuid.uuid4(),
            screen_id=screen.id,
            label=label,
            seat_count=24,
            price_paise=20000,
        )
        session.add(row)
        await session.flush()

        for num in range(1, 25):
            code = f"{label}{num:02d}"
            all_seats.append(
                Seat(id=uuid.uuid4(), row_id=row.id, number=num, code=code, x=num - 1, label=code)
            )

    session.add_all(all_seats)
    await session.commit()

    seat_count = (await session.execute(select(func.count()).select_from(Seat))).scalar()
    assert seat_count == 240

    sample_codes = (await session.execute(select(Seat.code).where(Seat.row_id == all_seats[0].row_id).order_by(Seat.number.asc()))).scalars().all()
    assert sample_codes[0] == "A01"
    assert sample_codes[-1] == "A24"

    first_row_id = all_seats[0].row_id
    duplicate_seat = Seat(id=uuid.uuid4(), row_id=first_row_id, number=99, code="A01", x=99)
    session.add(duplicate_seat)
    with pytest.raises(IntegrityError):
        await session.commit()


# ---------------------------------------------------------------------------
# M2 — same seat booked on two different showtimes of one screen -> both succeed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m2_same_seat_different_showtimes(session: AsyncSession):
    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="V1", city="Kochi", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="SCR1", total_seats=1)
    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=1, price_paise=10000)
    seat = Seat(id=uuid.uuid4(), row_id=row.id, number=1, code="A01", x=0)
    movie = Movie(id=uuid.uuid4(), title="M1", language="Malayalam", duration_min=120, certificate="U", partner_id=partner_id)
    session.add_all([venue, screen, row, seat, movie])
    await session.flush()

    now = datetime.now(timezone.utc)
    st1 = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=now, partner_id=partner_id)
    st2 = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=now, partner_id=partner_id)
    session.add_all([st1, st2])
    await session.flush()

    state1 = SeatState(showtime_id=st1.id, seat_id=seat.id, status=SeatStateStatus.BOOKED.value, booking_id=uuid.uuid4())
    state2 = SeatState(showtime_id=st2.id, seat_id=seat.id, status=SeatStateStatus.BOOKED.value, booking_id=uuid.uuid4())
    session.add_all([state1, state2])
    await session.commit()


# ---------------------------------------------------------------------------
# M3 — same seat, same showtime, twice -> DB raises IntegrityError
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m3_same_seat_same_showtime_duplicate_db_integrity_error(session: AsyncSession):
    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="V1", city="Kochi", partner_id=partner_id)
    session.add(venue)
    await session.flush()

    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="SCR1")
    session.add(screen)
    await session.flush()

    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=1, price_paise=10000)
    session.add(row)
    await session.flush()

    seat = Seat(id=uuid.uuid4(), row_id=row.id, number=1, code="A01", x=0)
    movie = Movie(id=uuid.uuid4(), title="M1", language="Malayalam", duration_min=120, certificate="U", partner_id=partner_id)
    session.add_all([seat, movie])
    await session.flush()

    st = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=datetime.now(timezone.utc), partner_id=partner_id)
    session.add(st)
    await session.flush()

    s1 = SeatState(showtime_id=st.id, seat_id=seat.id, status=SeatStateStatus.BOOKED.value, booking_id=uuid.uuid4())
    session.add(s1)
    await session.commit()

    s2 = SeatState(showtime_id=st.id, seat_id=seat.id, status=SeatStateStatus.BOOKED.value, booking_id=uuid.uuid4())
    session.add(s2)
    with pytest.raises(IntegrityError):
        await session.commit()

# ---------------------------------------------------------------------------
# M4 — block a seat -> booking refused; unblock -> bookable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m4_seat_blocking_lifecycle(session: AsyncSession, engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async def override_get_db():
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db

    from app.partner.models import PartnerORM

    partner = User(id=uuid.uuid4(), full_name="Test User", email="p4@pvr.local", password_hash="h", role="PARTNER")
    session.add(partner)
    await session.flush()

    partner_record = PartnerORM(
        id=uuid.uuid4(), user_id=partner.id, business_name="Test Cinema",
        partner_type="event_organiser", contact_name="Test User",
        contact_phone="9999999999", city="Kochi", status="APPROVED",
    )
    session.add(partner_record)
    await session.flush()

    venue = Venue(id=uuid.uuid4(), name="V1", city="Kochi", partner_id=partner.id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="SCR1")
    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=1, price_paise=10000)
    seat = Seat(id=uuid.uuid4(), row_id=row.id, number=1, code="A01", x=0)
    movie = Movie(id=uuid.uuid4(), title="M1", language="Malayalam", duration_min=120, certificate="U", partner_id=partner.id)
    st = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=datetime.now(timezone.utc), partner_id=partner.id)
    session.add_all([venue, screen, row, seat, movie, st])
    await session.commit()

    token = _token_for(partner.id, role="PARTNER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        block_resp = await client.patch(
            f"/v1/partner/showtimes/{st.id}/seats/block",
            json={"seat_ids": [str(seat.id)], "reason": "Maintenance"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert block_resp.status_code == 200

        cust_user = User(id=uuid.uuid4(), full_name="Cust", email="cust4@pvr.local", password_hash="h", role="USER")
        session.add(cust_user)
        await session.commit()
        cust_token = _token_for(cust_user.id, role="USER")
        book_resp = await client.post(
            "/v1/bookings",
            json={"showtime_id": str(st.id), "seat_ids": [str(seat.id)]},
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert book_resp.status_code == 409

        unblock_resp = await client.patch(
            f"/v1/partner/showtimes/{st.id}/seats/unblock",
            json={"seat_ids": [str(seat.id)]},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert unblock_resp.status_code == 200

        book_success = await client.post(
            "/v1/bookings",
            json={"showtime_id": str(st.id), "seat_ids": [str(seat.id)]},
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert book_success.status_code == 201

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# M5 — book, cancel, rebook the same seat on the same showtime -> succeeds
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m5_book_cancel_rebook_same_seat(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    user1 = User(id=uuid.uuid4(), full_name="Test User", email="u1@pvr.local", password_hash="h")
    user2 = User(id=uuid.uuid4(), full_name="Test User", email="u2@pvr.local", password_hash="h")
    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="V1", city="Kochi", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="SCR1")
    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=1, price_paise=10000)
    seat = Seat(id=uuid.uuid4(), row_id=row.id, number=1, code="A01", x=0)
    movie = Movie(id=uuid.uuid4(), title="M1", language="Malayalam", duration_min=120, certificate="U", partner_id=partner_id)
    st = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=datetime.now(timezone.utc), partner_id=partner_id)
    session.add_all([user1, user2, venue, screen, row, seat, movie, st])
    await session.commit()

    tok1 = _token_for(user1.id)
    tok2 = _token_for(user2.id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        b1 = await client.post(
            "/v1/bookings",
            json={"showtime_id": str(st.id), "seat_ids": [str(seat.id)]},
            headers={"Authorization": f"Bearer {tok1}"},
        )
        assert b1.status_code == 201
        booking_id = b1.json()["booking"]["id"]

        c1 = await client.patch(
            f"/v1/bookings/{booking_id}/cancel",
            headers={"Authorization": f"Bearer {tok1}"},
        )
        assert c1.status_code == 200

        b2 = await client.post(
            "/v1/bookings",
            json={"showtime_id": str(st.id), "seat_ids": [str(seat.id)]},
            headers={"Authorization": f"Bearer {tok2}"},
        )
        assert b2.status_code == 201

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# M6 — alembic revision --autogenerate on current models -> empty upgrade()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m6_alembic_autogenerate_empty(tmp_path, engine):
    test_db_url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://postgres:postgres@localhost:5432/test_db",
    )
    sync_url = test_db_url.replace("+asyncpg", "").replace("+aiosqlite", "")

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", sync_url)

    eng = create_engine(sync_url)
    with eng.connect() as conn:
        mc = MigrationContext.configure(conn, opts={"target_metadata": Base.metadata})
        diff = compare_metadata(mc, Base.metadata)

    eng.dispose()

    real_diff = [
        d for d in diff if not (d[0] in ("add_constraint", "remove_constraint") and "CHECK" in str(d).upper())
    ]
    assert not real_diff, f"Autogenerate found schema drift:\n{real_diff}"


# ---------------------------------------------------------------------------
# M7 — 20 concurrent attempts, one seat, 5 winners -> exactly 5 bookings
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m7_concurrent_booking_attempts(session: AsyncSession, engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker

    async def override_get_db():
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = override_get_db

    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="V1", city="Kochi", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="SCR1")
    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=5, price_paise=10000)
    seats = [
        Seat(id=uuid.uuid4(), row_id=row.id, number=n, code=f"A{n:02d}", x=n - 1)
        for n in range(1, 6)
    ]
    movie = Movie(id=uuid.uuid4(), title="M1", language="Malayalam", duration_min=120, certificate="U", partner_id=partner_id)
    st = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=datetime.now(timezone.utc), partner_id=partner_id)

    users = [User(id=uuid.uuid4(), full_name="Test User", email=f"u{i}@pvr.local", password_hash="h") for i in range(20)]
    session.add_all([venue, screen, row, movie, st] + seats + users)
    await session.commit()

    tokens = [_token_for(u.id) for u in users]

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async def try_book(tok, seat_obj):
            return await client.post(
                "/v1/bookings",
                json={"showtime_id": str(st.id), "seat_ids": [str(seat_obj.id)]},
                headers={"Authorization": f"Bearer {tok}"},
            )

        tasks = [try_book(tokens[i], seats[i % 5]) for i in range(20)]
        results = await asyncio.gather(*tasks)

        successes = [r for r in results if r.status_code == 201]
        assert len(successes) == 5

        state_count = (
            await session.execute(
                select(func.count())
                .select_from(SeatState)
                .where(SeatState.showtime_id == st.id)
            )
        ).scalar()
        assert state_count == 5

    app.dependency_overrides.clear()
