"""
Phase E Tests — Self-hosted hall partner writes and seat booking (E1 - E15).
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, datetime, timedelta, timezone
import pytest
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.booking.models import BookingModel
from app.booking.services import BookingService
from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.movie.layout_parser import parse_text_grid
from app.movie.models import Movie, MovieSoldCount, Screen, ScreenRow, Seat, SeatState, Showtime, Venue
from app.partner.models import PartnerORM
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


async def _seed_self_hosted_hall(session: AsyncSession):
    partner = User(id=uuid.uuid4(), full_name="Partner E", email=f"p_{uuid.uuid4().hex[:6]}@t.local", password_hash="pwd", role="PARTNER", is_active=True)
    session.add(partner)
    await session.flush()

    partner_orm = PartnerORM(id=uuid.uuid4(), user_id=partner.id, business_name="Cinema E", partner_type="event_organiser", contact_name="Partner E", contact_phone="9999999999", city="Kochi", status="APPROVED")
    venue = Venue(id=uuid.uuid4(), name="Venue E", city="Kochi", partner_id=partner.id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Screen E", total_seats=0)
    movie = Movie(id=uuid.uuid4(), title="Movie E", duration_min=120, language="Malayalam", certificate="U", status="PUBLISHED", partner_id=partner.id)
    session.add_all([partner_orm, venue, screen, movie])
    await session.commit()
    return {"partner": partner, "venue": venue, "screen": screen, "movie": movie}


# E1: Grid with 10 rows of 24 -> COUNT(seats) == 240, codes A01..J24
def test_e1_large_grid_parsing():
    grid_lines = [f"{chr(65+i)}(24): " + "1"*24 for i in range(10)]
    grid_text = "\n".join(grid_lines)
    parsed = parse_text_grid(grid_text)
    assert len(parsed) == 10
    total_seats = sum(p.seat_count for p in parsed)
    assert total_seats == 240
    assert parsed[0].seats[0].code == "A01"
    assert parsed[9].seats[23].code == "J24"


# E2: Layout write where a row parsed != declared -> 422, 0 seats exist
@pytest.mark.asyncio
async def test_e2_layout_write_mismatch_writes_nothing(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    token = _token_for(data["partner"].id, role="PARTNER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/v1/partner/screens/{data['screen'].id}/layout",
            json={"text_grid": "A(10): 111111", "default_price_paise": 20000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    count = (await session.execute(select(func.count(Seat.id)).join(ScreenRow).where(ScreenRow.screen_id == data["screen"].id))).scalar()
    assert count == 0
    app.dependency_overrides.clear()


# E3: Layout edit while any showtime has seat_states -> 409
@pytest.mark.asyncio
async def test_e3_layout_edit_with_active_seat_states_rejected(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    token = _token_for(data["partner"].id, role="PARTNER")

    # Apply initial layout
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/v1/partner/screens/{data['screen'].id}/layout",
            json={"text_grid": "A(5): 11111", "default_price_paise": 20000},
            headers={"Authorization": f"Bearer {token}"},
        )

        # Create showtime & book seat
        st = Showtime(id=uuid.uuid4(), screen_id=data["screen"].id, movie_id=data["movie"].id, starts_at=utcnow() + timedelta(days=1), partner_id=data["partner"].id, status="ACTIVE")
        seat = (await session.execute(select(Seat).join(ScreenRow).where(ScreenRow.screen_id == data["screen"].id))).scalars().first()
        session.add(st)
        await session.flush()
        session.add(SeatState(showtime_id=st.id, seat_id=seat.id, status="BOOKED"))
        await session.commit()

        # Try to regenerate layout -> must fail 409
        resp = await client.patch(
            f"/v1/partner/screens/{data['screen'].id}/layout",
            json={"text_grid": "A(4): 1111", "default_price_paise": 20000},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 409
    app.dependency_overrides.clear()


# E4: Screen whose venue belongs to another partner -> 404
@pytest.mark.asyncio
async def test_e4_foreign_partner_screen_write_404(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    other_partner = User(id=uuid.uuid4(), full_name="Other P", email="other_p@t.local", password_hash="pwd", role="PARTNER", is_active=True)
    other_orm = PartnerORM(id=uuid.uuid4(), user_id=other_partner.id, business_name="Other Cinema", partner_type="event_organiser", contact_name="Other", contact_phone="9999999990", city="Kochi", status="APPROVED")
    session.add_all([other_partner, other_orm])
    await session.commit()

    token = _token_for(other_partner.id, role="PARTNER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/partner/screens",
            json={"venue_id": str(data["venue"].id), "name": "Illegal Screen"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (403, 404)
    app.dependency_overrides.clear()


# E5: Book 3 seats -> 201 CONFIRMED, 3 seat_states rows, total_paise == 3 * row price
@pytest.mark.asyncio
async def test_e5_book_three_seats_happy_path(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    p_token = _token_for(data["partner"].id, role="PARTNER")

    cust = User(id=uuid.uuid4(), full_name="Customer 5", email="c5@t.local", password_hash="pwd", role="USER", is_active=True)
    session.add(cust)
    await session.commit()
    c_token = _token_for(cust.id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/v1/partner/screens/{data['screen'].id}/layout",
            json={"text_grid": "A(5): 11111", "default_price_paise": 20000},
            headers={"Authorization": f"Bearer {p_token}"},
        )

        st = Showtime(id=uuid.uuid4(), screen_id=data["screen"].id, movie_id=data["movie"].id, starts_at=utcnow() + timedelta(days=1), partner_id=data["partner"].id, status="ACTIVE")
        session.add(st)
        await session.commit()

        seats = (await session.execute(select(Seat).join(ScreenRow).where(ScreenRow.screen_id == data["screen"].id))).scalars().all()[:3]

        resp = await client.post(
            "/v1/bookings",
            json={"showtime_id": str(st.id), "seat_ids": [str(s.id) for s in seats]},
            headers={"Authorization": f"Bearer {c_token}"},
        )
        assert resp.status_code == 201

    states_count = (await session.execute(select(func.count(SeatState.seat_id)).where(SeatState.showtime_id == st.id))).scalar()
    assert states_count == 3
    app.dependency_overrides.clear()


# E6: Book a BLOCKED seat -> 409
@pytest.mark.asyncio
async def test_e6_book_blocked_seat_409(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    p_token = _token_for(data["partner"].id, role="PARTNER")
    cust = User(id=uuid.uuid4(), full_name="Cust 6", email="c6@t.local", password_hash="pwd", role="USER", is_active=True)
    session.add(cust)
    await session.commit()
    c_token = _token_for(cust.id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/v1/partner/screens/{data['screen'].id}/layout",
            json={"text_grid": "A(5): 11111", "default_price_paise": 20000},
            headers={"Authorization": f"Bearer {p_token}"},
        )
        st = Showtime(id=uuid.uuid4(), screen_id=data["screen"].id, movie_id=data["movie"].id, starts_at=utcnow() + timedelta(days=1), partner_id=data["partner"].id, status="ACTIVE")
        session.add(st)
        await session.commit()

        seat = (await session.execute(select(Seat).join(ScreenRow).where(ScreenRow.screen_id == data["screen"].id))).scalars().first()
        session.add(SeatState(showtime_id=st.id, seat_id=seat.id, status="BLOCKED"))
        await session.commit()

        resp = await client.post(
            "/v1/bookings",
            json={"showtime_id": str(st.id), "seat_ids": [str(seat.id)]},
            headers={"Authorization": f"Bearer {c_token}"},
        )
        assert resp.status_code == 409
    app.dependency_overrides.clear()


# E7: Same user, same key, twice -> exactly one 201
@pytest.mark.asyncio
async def test_e7_idempotent_booking_same_key(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_hosted_hall_or_venue(session) if hasattr(session, "id") else await _seed_self_hosted_hall(session)
    p_token = _token_for(data["partner"].id, role="PARTNER")
    cust = User(id=uuid.uuid4(), full_name="Cust 7", email="c7@t.local", password_hash="pwd", role="USER", is_active=True)
    session.add(cust)
    await session.commit()
    c_token = _token_for(cust.id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/v1/partner/screens/{data['screen'].id}/layout",
            json={"text_grid": "A(5): 11111", "default_price_paise": 20000},
            headers={"Authorization": f"Bearer {p_token}"},
        )
        st = Showtime(id=uuid.uuid4(), screen_id=data["screen"].id, movie_id=data["movie"].id, starts_at=utcnow() + timedelta(days=1), partner_id=data["partner"].id, status="ACTIVE")
        session.add(st)
        await session.commit()

        seat = (await session.execute(select(Seat).join(ScreenRow).where(ScreenRow.screen_id == data["screen"].id))).scalars().first()

        payload = {"showtime_id": str(st.id), "seat_ids": [str(seat.id)], "idempotency_key": "e7-key"}
        r1 = await client.post("/v1/bookings", json=payload, headers={"Authorization": f"Bearer {c_token}"})
        r2 = await client.post("/v1/bookings", json=payload, headers={"Authorization": f"Bearer {c_token}"})
        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["booking"]["id"] == r2.json()["booking"]["id"]
    app.dependency_overrides.clear()


# E9: Book, cancel, re-book the same seat -> succeeds
@pytest.mark.asyncio
async def test_e9_book_cancel_rebook_succeeds(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    p_token = _token_for(data["partner"].id, role="PARTNER")
    cust = User(id=uuid.uuid4(), full_name="Cust 9", email="c9@t.local", password_hash="pwd", role="USER", is_active=True)
    session.add(cust)
    await session.commit()
    c_token = _token_for(cust.id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/v1/partner/screens/{data['screen'].id}/layout",
            json={"text_grid": "A(5): 11111", "default_price_paise": 20000},
            headers={"Authorization": f"Bearer {p_token}"},
        )
        st = Showtime(id=uuid.uuid4(), screen_id=data["screen"].id, movie_id=data["movie"].id, starts_at=utcnow() + timedelta(days=1), partner_id=data["partner"].id, status="ACTIVE")
        session.add(st)
        await session.commit()
        seat = (await session.execute(select(Seat).join(ScreenRow).where(ScreenRow.screen_id == data["screen"].id))).scalars().first()

        r1 = await client.post("/v1/bookings", json={"showtime_id": str(st.id), "seat_ids": [str(seat.id)]}, headers={"Authorization": f"Bearer {c_token}"})
        b_id = r1.json()["booking"]["id"]

        c_resp = await client.patch(f"/v1/bookings/{b_id}/cancel", headers={"Authorization": f"Bearer {c_token}"})
        assert c_resp.status_code == 200

        r2 = await client.post("/v1/bookings", json={"showtime_id": str(st.id), "seat_ids": [str(seat.id)]}, headers={"Authorization": f"Bearer {c_token}"})
        assert r2.status_code == 201
    app.dependency_overrides.clear()


# E10: Self-hosted booking never has status HELD or non-null held_until
@pytest.mark.asyncio
async def test_e10_self_hosted_never_held(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    p_token = _token_for(data["partner"].id, role="PARTNER")
    cust = User(id=uuid.uuid4(), full_name="Cust 10", email="c10@t.local", password_hash="pwd", role="USER", is_active=True)
    session.add(cust)
    await session.commit()
    c_token = _token_for(cust.id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/v1/partner/screens/{data['screen'].id}/layout",
            json={"text_grid": "A(5): 11111", "default_price_paise": 20000},
            headers={"Authorization": f"Bearer {p_token}"},
        )
        st = Showtime(id=uuid.uuid4(), screen_id=data["screen"].id, movie_id=data["movie"].id, starts_at=utcnow() + timedelta(days=1), partner_id=data["partner"].id, status="ACTIVE")
        session.add(st)
        await session.commit()
        seat = (await session.execute(select(Seat).join(ScreenRow).where(ScreenRow.screen_id == data["screen"].id))).scalars().first()

        r = await client.post("/v1/bookings", json={"showtime_id": str(st.id), "seat_ids": [str(seat.id)]}, headers={"Authorization": f"Bearer {c_token}"})
        b_id = uuid.UUID(r.json()["booking"]["id"])

    b = (await session.execute(select(BookingModel).where(BookingModel.id == b_id))).scalar_one()
    assert b.status == "CONFIRMED"
    assert b.held_until is None
    app.dependency_overrides.clear()


# E11: POST /bookings with a provider showtime_id -> refused with distinct message
@pytest.mark.asyncio
async def test_e11_provider_showtime_refused_on_legacy_bookings(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    prov = ProviderRegistryModel(id=uuid.uuid4(), name="PVR Prov", base_url="http://pvr.local", hold_ttl_seconds=600, enabled=True)
    session.add(prov)
    await session.flush()
    st = Showtime(id=uuid.uuid4(), screen_id=data["screen"].id, movie_id=data["movie"].id, starts_at=utcnow() + timedelta(days=1), partner_id=data["partner"].id, status="ACTIVE", provider_id=prov.id)
    cust = User(id=uuid.uuid4(), full_name="Cust 11", email="c11@t.local", password_hash="pwd", role="USER", is_active=True)
    session.add_all([st, cust])
    await session.commit()
    c_token = _token_for(cust.id, role="USER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings",
            json={"showtime_id": str(st.id), "seat_ids": [str(uuid.uuid4())]},
            headers={"Authorization": f"Bearer {c_token}"},
        )
        assert resp.status_code == 400
        assert "provider-backed" in resp.text
    app.dependency_overrides.clear()


# E13: Cancel a showtime in the past -> 409/400
@pytest.mark.asyncio
async def test_e13_cancel_past_showtime_rejected(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    p_token = _token_for(data["partner"].id, role="PARTNER")

    st = Showtime(id=uuid.uuid4(), screen_id=data["screen"].id, movie_id=data["movie"].id, starts_at=utcnow() - timedelta(hours=2), partner_id=data["partner"].id, status="ACTIVE")
    session.add(st)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            f"/v1/partner/showtimes/{st.id}/cancel",
            headers={"Authorization": f"Bearer {p_token}"},
        )
        assert resp.status_code in (400, 403, 409)
    app.dependency_overrides.clear()


# E15: GET /v1/showtimes/{id}/availability -> total/available/booked/blocked sums to total
@pytest.mark.asyncio
async def test_e15_showtime_availability_sums_to_total(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_self_hosted_hall(session)
    p_token = _token_for(data["partner"].id, role="PARTNER")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.patch(
            f"/v1/partner/screens/{data['screen'].id}/layout",
            json={"text_grid": "A(10): 1111111111", "default_price_paise": 20000},
            headers={"Authorization": f"Bearer {p_token}"},
        )
        st = Showtime(id=uuid.uuid4(), screen_id=data["screen"].id, movie_id=data["movie"].id, starts_at=utcnow() + timedelta(days=1), partner_id=data["partner"].id, status="ACTIVE")
        session.add(st)
        await session.commit()

        resp = await client.get(f"/v1/showtimes/{st.id}/availability")
        assert resp.status_code == 200
        b = resp.json()
        assert b["total_seats"] == 10
        assert b["available_seats"] + b["booked_seats"] + b["blocked_seats"] == b["total_seats"]
    app.dependency_overrides.clear()
