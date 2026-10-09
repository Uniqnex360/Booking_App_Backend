import uuid
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.auth.models import User
from app.booking.models import BookingModel
from app.core.database import get_db
from app.fnb.models import FnbItemModel, BookingFnbModel
from app.main import app
from app.movie.models import Movie, Screen, Showtime, Venue
from app.partner.models import PartnerORM
from app.shared.timeutil import utcnow

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client(session):
    app.dependency_overrides[get_db] = lambda: session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest_asyncio.fixture
async def auth_user(session):
    u = User(
        id=uuid.uuid4(),
        full_name="FNB User",
        email=f"fnb_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="pwd",
        role="USER",
        is_active=True,
    )
    session.add(u)
    await session.commit()
    return u


@pytest_asyncio.fixture
def auth_headers(auth_user):
    from app.auth.security import JWTTokenService
    token = JWTTokenService().create_access_token(auth_user)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def other_user_auth_headers(session):
    u = User(
        id=uuid.uuid4(),
        full_name="Other User",
        email=f"other_{uuid.uuid4().hex[:6]}@example.com",
        password_hash="pwd",
        role="USER",
        is_active=True,
    )
    session.add(u)
    await session.commit()
    from app.auth.security import JWTTokenService
    token = JWTTokenService().create_access_token(u)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def setup_fnb_base(session, auth_user):
    partner = User(id=uuid.uuid4(), full_name="Partner FNB", email=f"p_{uuid.uuid4().hex[:6]}@t.local", password_hash="pwd", role="PARTNER", is_active=True)
    session.add(partner)
    await session.flush()

    partner_orm = PartnerORM(id=uuid.uuid4(), user_id=partner.id, business_name="Cinema FNB", partner_type="event_organiser", contact_name="Partner FNB", contact_phone="9999999999", city="Kochi", status="APPROVED")
    venue = Venue(id=uuid.uuid4(), name="Venue FNB", city="Kochi", partner_id=partner.id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Screen FNB", total_seats=100)
    movie = Movie(id=uuid.uuid4(), title="Movie FNB", duration_min=120, language="Malayalam", certificate="U", status="PUBLISHED", partner_id=partner.id)
    session.add_all([partner_orm, venue, screen, movie])
    await session.flush()

    now = utcnow()
    showtime = Showtime(
        id=uuid.uuid4(),
        movie_id=movie.id,
        screen_id=screen.id,
        partner_id=partner.id,
        starts_at=now + timedelta(hours=2),
        status="ACTIVE",
    )
    session.add(showtime)
    await session.flush()

    item = FnbItemModel(
        id=uuid.uuid4(),
        venue_id=venue.id,
        name="Tub Popcorn",
        category="Popcorn",
        price_paise=13000,
        is_active=True,
    )
    session.add(item)
    await session.commit()
    return {"venue": venue, "screen": screen, "movie": movie, "showtime": showtime, "item": item}


@pytest_asyncio.fixture
async def seed_fnb_item(setup_fnb_base):
    return setup_fnb_base["item"].id


@pytest_asyncio.fixture
async def seed_other_venue_item(session):
    partner = User(id=uuid.uuid4(), full_name="Partner Other", email=f"p_{uuid.uuid4().hex[:6]}@t.local", password_hash="pwd", role="PARTNER", is_active=True)
    session.add(partner)
    await session.flush()
    partner_orm = PartnerORM(id=uuid.uuid4(), user_id=partner.id, business_name="Cinema Other", partner_type="event_organiser", contact_name="Partner", contact_phone="9999999999", city="Kochi", status="APPROVED")
    venue = Venue(id=uuid.uuid4(), name="Other Venue", city="Kochi", partner_id=partner.id)
    session.add_all([partner_orm, venue])
    await session.flush()
    item = FnbItemModel(
        id=uuid.uuid4(),
        venue_id=venue.id,
        name="Nachos",
        category="Snacks",
        price_paise=15000,
        is_active=True,
    )
    session.add(item)
    await session.commit()
    return item.id


@pytest_asyncio.fixture
async def seed_movie_booking(session, auth_user, setup_fnb_base):
    st = setup_fnb_base["showtime"]
    item = setup_fnb_base["item"]
    booking = BookingModel(
        id=uuid.uuid4(),
        user_id=auth_user.id,
        booking_type="MOVIE",
        showtime_id=st.id,
        ticket_paise=20000,
        fnb_paise=0,
        convenience_fee_paise=0,
        total_paise=20000,
        currency="INR",
        status="HELD",
        held_until=utcnow() + timedelta(minutes=10),
        ref_code=f"BK{uuid.uuid4().hex[:12].upper()}",
    )
    session.add(booking)
    await session.commit()
    return booking.id, item.id


@pytest_asyncio.fixture
async def seed_movie_booking_with_fnb(session, auth_user, setup_fnb_base):
    st = setup_fnb_base["showtime"]
    item = setup_fnb_base["item"]
    booking = BookingModel(
        id=uuid.uuid4(),
        user_id=auth_user.id,
        booking_type="MOVIE",
        showtime_id=st.id,
        ticket_paise=20000,
        fnb_paise=13000,
        convenience_fee_paise=0,
        total_paise=33000,
        currency="INR",
        status="HELD",
        held_until=utcnow() + timedelta(minutes=10),
        ref_code=f"BK{uuid.uuid4().hex[:12].upper()}",
    )
    session.add(booking)
    await session.flush()
    fnb_line = BookingFnbModel(
        booking_id=booking.id,
        item_id=item.id,
        quantity=1,
        unit_price_paise=13000,
    )
    session.add(fnb_line)
    await session.commit()
    return booking.id, item.id


@pytest_asyncio.fixture
async def seed_expired_hold(session, auth_user, setup_fnb_base):
    st = setup_fnb_base["showtime"]
    booking = BookingModel(
        id=uuid.uuid4(),
        user_id=auth_user.id,
        booking_type="MOVIE",
        showtime_id=st.id,
        ticket_paise=20000,
        fnb_paise=0,
        convenience_fee_paise=0,
        total_paise=20000,
        currency="INR",
        status="HELD",
        held_until=utcnow() - timedelta(minutes=5),
        ref_code=f"BK{uuid.uuid4().hex[:12].upper()}",
    )
    session.add(booking)
    await session.commit()
    return booking.id


async def test_fnb_menu_returns_empty_for_unknown_showtime(client: AsyncClient):
    r = await client.get("/v1/showtimes/00000000-0000-0000-0000-000000000000/fnb-menu")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["data"]["items"] == []


async def test_replace_fnb_recomputes_total(
    client: AsyncClient, seed_movie_booking, auth_headers
):
    """Add 2x Tub Popcorn (₹130) to a HELD booking whose ticket_paise is 20000.
    fnb_paise must be 26000, total_paise 46000."""
    booking_id, item_id = seed_movie_booking

    r = await client.put(
        f"/v1/bookings/{booking_id}/fnb",
        json={"items": [{"item_id": str(item_id), "quantity": 2}]},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["fnb_paise"] == 26000
    assert body["total_paise"] == 46000
    assert len(body["fnb_lines"]) == 1
    assert body["fnb_lines"][0]["quantity"] == 2
    assert body["fnb_lines"][0]["unit_price_paise"] == 13000


async def test_replace_fnb_empty_clears(
    client: AsyncClient, seed_movie_booking_with_fnb, auth_headers
):
    booking_id, _ = seed_movie_booking_with_fnb
    r = await client.put(
        f"/v1/bookings/{booking_id}/fnb",
        json={"items": []},
        headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["fnb_paise"] == 0
    assert body["total_paise"] == body["ticket_paise"] + body["convenience_fee_paise"]


async def test_wrong_venue_item_rejected(
    client: AsyncClient, seed_movie_booking, seed_other_venue_item, auth_headers
):
    booking_id, _ = seed_movie_booking
    other_item_id = seed_other_venue_item

    r = await client.put(
        f"/v1/bookings/{booking_id}/fnb",
        json={"items": [{"item_id": str(other_item_id), "quantity": 1}]},
        headers=auth_headers,
    )
    assert r.status_code == 422


async def test_expired_hold_rejected(
    client: AsyncClient, seed_expired_hold, auth_headers, seed_fnb_item
):
    booking_id = seed_expired_hold
    item_id = seed_fnb_item
    r = await client.put(
        f"/v1/bookings/{booking_id}/fnb",
        json={"items": [{"item_id": str(item_id), "quantity": 1}]},
        headers=auth_headers,
    )
    assert r.status_code == 409
    assert r.json()["error"]["type"] == "HOLD_EXPIRED"


async def test_other_user_gets_404(
    client: AsyncClient, seed_movie_booking, other_user_auth_headers, seed_fnb_item
):
    booking_id, _ = seed_movie_booking
    r = await client.put(
        f"/v1/bookings/{booking_id}/fnb",
        json={"items": [{"item_id": str(seed_fnb_item), "quantity": 1}]},
        headers=other_user_auth_headers,
    )
    assert r.status_code == 404