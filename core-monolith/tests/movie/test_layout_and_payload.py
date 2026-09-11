"""
Tests M11, M13–M15: Seat-map projections, text-grid parser edge cases, sections, and validation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.services import AuthService
from app.core.config import settings
from app.core.database import Base, get_db
from app.main import app
from app.movie.layout_parser import LayoutParseError, parse_text_grid
from app.movie.models import (
    Movie,
    MovieStatus,
    Screen,
    ScreenRow,
    Seat,
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
# M11 — seat-map payload: id, code, x, status, price_paise; none BOOKED pre-booking
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m11_seat_map_payload_structure(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="V1", city="Kochi", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="SCR1", total_seats=5)
    row = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", seat_count=5, price_paise=25000)
    seats = [
        Seat(id=uuid.uuid4(), row_id=row.id, number=n, code=f"A{n:02d}", x=n - 1)
        for n in range(1, 6)
    ]
    movie = Movie(
        id=uuid.uuid4(),
        title="M11 Film",
        language="Malayalam",
        duration_min=120,
        certificate="UA",
        status=MovieStatus.PUBLISHED.value,
        partner_id=partner_id,
    )
    st = Showtime(
        id=uuid.uuid4(),
        screen_id=screen.id,
        movie_id=movie.id,
        starts_at=datetime.now(timezone.utc),
        partner_id=partner_id,
    )

    session.add_all([venue, screen, row, movie, st] + seats)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/showtimes/{st.id}/seat-map")
        assert resp.status_code == 200
        payload = resp.json()

        assert "rows" in payload
        row_data = payload["rows"][0]
        assert row_data["price_paise"] == 25000

        for seat_data in row_data["seats"]:
            assert "seat_id" in seat_data or "id" in seat_data
            assert "code" in seat_data
            assert "x" in seat_data
            assert "status" in seat_data
            assert "price_paise" in seat_data
            assert seat_data["status"] == "AVAILABLE"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# M13 — grid "C: -1111 2 1111-" -> right seat count, non-contiguous x
# ---------------------------------------------------------------------------

def test_m13_text_grid_parser_gaps_and_non_contiguous_x():
    grid = "C: -1111 2 1111-"
    parsed = parse_text_grid(grid)
    assert len(parsed) == 1

    row = parsed[0]
    assert row.label == "C"
    assert row.seat_count == 8

    assert row.seats[0].number == 1
    assert row.seats[0].code == "C01"
    assert row.seats[0].x == 1

    assert row.seats[3].x == 4

    assert row.seats[4].number == 5
    assert row.seats[4].code == "C05"
    assert row.seats[4].x == 7


# ---------------------------------------------------------------------------
# M14 — rows in two sections -> payload groups by section; one booking spans both
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_m14_multi_section_booking_across_stalls_and_balcony(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="V1", city="Kochi", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="SCR1", total_seats=2)

    row_stalls = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="A", section="STALLS", seat_count=1, price_paise=15000)
    seat_stalls = Seat(id=uuid.uuid4(), row_id=row_stalls.id, number=1, code="A01", x=0)

    row_balcony = ScreenRow(id=uuid.uuid4(), screen_id=screen.id, label="B", section="BALCONY", seat_count=1, price_paise=30000)
    seat_balcony = Seat(id=uuid.uuid4(), row_id=row_balcony.id, number=1, code="B01", x=0)

    movie = Movie(id=uuid.uuid4(), title="M14 Film", language="Malayalam", duration_min=120, certificate="UA", status=MovieStatus.PUBLISHED.value, partner_id=partner_id)
    st = Showtime(id=uuid.uuid4(), screen_id=screen.id, movie_id=movie.id, starts_at=datetime.now(timezone.utc), partner_id=partner_id)

    cust_user = User(id=uuid.uuid4(), full_name="Cust", email="m14cust@pvr.local", password_hash="h", role="USER")
    session.add_all([venue, screen, row_stalls, seat_stalls, row_balcony, seat_balcony, movie, st, cust_user])
    await session.commit()

    cust_token = _token_for(cust_user.id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        sm_resp = await client.get(f"/v1/showtimes/{st.id}/seat-map")
        assert sm_resp.status_code == 200
        sections = [r["section"] for r in sm_resp.json()["rows"]]
        assert "STALLS" in sections
        assert "BALCONY" in sections

        book_resp = await client.post(
            "/v1/bookings",
            json={"showtime_id": str(st.id), "seat_ids": [str(seat_stalls.id), str(seat_balcony.id)]},
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert book_resp.status_code == 201

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# M15 — grid row of 12 where seat_count says 10 -> validation error
# ---------------------------------------------------------------------------

def test_m15_layout_grid_count_mismatch_raises_validation_error():
    with pytest.raises(LayoutParseError, match="seat count mismatch: declared 10, parsed 12"):
        parse_text_grid("A(10): 111111111111")
    with pytest.raises(LayoutParseError, match="seat count mismatch: declared 10, parsed 8"):
        parse_text_grid("A(10): 11111111")
    with pytest.raises(LayoutParseError, match="seat count mismatch: declared 10, parsed 12"):
        parse_text_grid("A: 111111111111", expected_row_counts={"A": 10})
    rows = parse_text_grid("A(10): 1111111111")
    assert len(rows) == 1
    assert rows[0].seat_count == 10

@pytest.mark.asyncio
async def test_m15_layout_refusal_writes_nothing(session):
    from app.core.database import get_db
    from app.auth.models import User
    from app.movie.models import Venue, Screen, ScreenRow
    from sqlalchemy import select, func
    app.dependency_overrides[get_db] = lambda: session
    partner = User(id=uuid.uuid4(), full_name="Test Partner", email="p_m15@test.local", password_hash="h", role="PARTNER")
    session.add(partner)
    await session.commit()
    from app.partner.models import PartnerORM
    partner_rec = PartnerORM(id=uuid.uuid4(), user_id=partner.id, business_name="Cinema 15", partner_type="event_organiser", contact_name="Partner", contact_phone="9876543210", city="Kochi", status="APPROVED")
    venue = Venue(id=uuid.uuid4(), name="Venue 15", city="Kochi", partner_id=partner.id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Screen 15", total_seats=0)
    session.add_all([partner_rec, venue, screen])
    await session.commit()
    token = _token_for(partner.id, role="PARTNER")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(f"/v1/partner/screens/{screen.id}/layout", json={"text_grid": "A(10): 111111111111", "default_price_paise": 25000}, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 422
    row_count = (await session.execute(select(func.count(ScreenRow.id)).where(ScreenRow.screen_id == screen.id))).scalar()
    assert row_count == 0
    app.dependency_overrides.clear()
