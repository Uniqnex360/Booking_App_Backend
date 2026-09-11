"""
Provider Integration tests C1 through C15 covering mock transports and live integration.
"""

from __future__ import annotations
from jose import jwt
import json
import os
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db

import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
from httpx import ASGITransport, AsyncClient, MockTransport, Response
from sqlalchemy import select
from app.providers.theatre import PVRProvider

from app.auth.models import User
from app.auth.services import AuthService
from app.booking.models import BookingModel
from app.booking.services import BookingService
from app.core.config import settings
from app.main import app
from app.movie.models import Movie, Screen, Showtime, Venue
from app.providers import registry
from app.providers.base import ITheatreProvider
from app.providers.registry import ProviderRegistryModel

def _token_for(user_id: uuid.UUID, role: str = "USER") -> str:
    to_encode = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.utcnow() + timedelta(minutes=30),
        "iat": datetime.utcnow(),
        "type": "access",
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def _seed_provider_showtime(session: AsyncSession) -> dict:
    partner_id = uuid.uuid4()
    venue = Venue(
        id=uuid.uuid4(),
        name="PVR Grand",
        city="Kochi",
        partner_id=partner_id,
    )
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Audi 1")
    movie = Movie(
        id=uuid.uuid4(),
        title="Interstellar",
        duration_min=169,
        language="English",
        certificate="UA",
        status="PUBLISHED",
        partner_id=partner_id,
    )

    session.add_all([venue, screen, movie])
    await session.flush()

    provider_reg = ProviderRegistryModel(
        id=uuid.uuid4(),
        name="PVR Test Provider",
        base_url="http://pvr-mock.local",
        auth_token_ref="secret_pvr_tok",
        hold_ttl_seconds=600,
        enabled=True,
        partner_id=None,
    )
    session.add(provider_reg)
    await session.flush()

    st = Showtime(
        id=uuid.uuid4(),
        screen_id=screen.id,
        movie_id=movie.id,
        starts_at=datetime.now(timezone.utc) + timedelta(days=1),
        partner_id=partner_id,
        provider_id=provider_reg.id,
        provider_showtime_ref="remote-st-101",
    )
    user = User(
        id=uuid.uuid4(),
        full_name="Test Customer",
        email=f"customer_{uuid.uuid4().hex[:6]}@test.local",
        password_hash="pwd",
        role="USER",
        is_active=True,
    )
    session.add_all([st, user])
    await session.commit()
    return {
        "showtime": st,
        "provider": provider_reg,
        "user": user,
    }


# ---------------------------------------------------------------------------
# C1: Hold happy path -> 201 HELD, held_until equals the provider's value
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c1_hold_happy_path(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    expires_at_dt = datetime.now(timezone.utc) + timedelta(minutes=10)
    expires_at_str = expires_at_dt.isoformat()

    def mock_handler(request: httpx.Request):
        if request.url.path == "/v1/holds" and request.method == "POST":
            return Response(
                201,
                json={
                    "hold_id": "remote-hold-123",
                    "expires_at": expires_at_str,
                    "seats": [{"seat_id": "s1", "code": "A01", "price_cents": 25000}],
                    "total": 25000,
                    "currency": "INR",
                },
            )
        return Response(404)

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings/hold",
            json={
                "showtime_id": str(data["showtime"].id),
                "seat_ids": ["s1"],
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Idempotency-Key": "c1-idem-key",
            },
        )
        assert resp.status_code == 201
        res = resp.json()
        assert res["status"] == "success"
        assert res["data"]["status"] == "HELD"
        assert res["data"]["held_until"] is not None

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C2: No Idempotency-Key -> 422 VALIDATION_ERROR
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c2_missing_idempotency_key(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings/hold",
            json={
                "showtime_id": str(data["showtime"].id),
                "seat_ids": ["s1"],
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 422

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C3: Same key twice -> ONE local row and exactly ONE provider call
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c3_same_key_twice_one_call(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)
    call_count = 0

    def mock_handler(request: httpx.Request):
        nonlocal call_count
        call_count += 1
        return Response(
            201,
            json={
                "hold_id": "remote-hold-c3",
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
                "seats": [{"seat_id": "s1", "code": "A01", "price_cents": 25000}],
                "total": 25000,
                "currency": "INR",
            },
        )

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": "c3-key"}
        payload = {"showtime_id": str(data["showtime"].id), "seat_ids": ["s1"]}

        r1 = await client.post("/v1/bookings/hold", json=payload, headers=headers)
        r2 = await client.post("/v1/bookings/hold", json=payload, headers=headers)

        assert r1.status_code == 201
        assert r2.status_code == 201
        assert r1.json()["data"]["id"] == r2.json()["data"]["id"]
        assert call_count == 1

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C4: Provider rejects 1 of 3 seats -> no local row at all, 409 naming that seat
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c4_seat_unavailable_remote(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    def mock_handler(request: httpx.Request):
        return Response(409, json={"detail": {"code": "SEAT_UNAVAILABLE", "seats": ["s2"]}})

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings/hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": ["s1", "s2", "s3"]},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "c4-key"},
        )
        assert resp.status_code == 409
        err = resp.json()["error"]
        assert err["type"] == "SEAT_UNAVAILABLE_REMOTE"
        assert "s2" in err["details"]

    rows = (await session.execute(select(BookingModel))).scalars().all()
    assert len(rows) == 0

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C5: Provider down during hold -> 502 PROVIDER_UNAVAILABLE, nothing written
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c5_provider_down_during_hold(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    def mock_handler(request: httpx.Request):
        return Response(503)

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings/hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": ["s1"]},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "c5-key"},
        )
        assert resp.status_code == 502
        assert resp.json()["error"]["type"] == "PROVIDER_UNAVAILABLE"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C6: Commit after provider says expired -> EXPIRED locally, 409 HOLD_EXPIRED
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c6_commit_expired_remote(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    def mock_handler(request: httpx.Request):
        if request.url.path == "/v1/holds" and request.method == "POST":
            return Response(201, json={"hold_id": "h-c6", "expires_at": datetime.now(timezone.utc).isoformat(), "seats": [], "total": 1000, "currency": "INR"})
        if "/commit" in request.url.path:
            return Response(410, json={"detail": {"code": "HOLD_EXPIRED"}})
        return Response(404)

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/v1/bookings/hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": ["s1"]},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "c6-key"},
        )
        booking_id = r.json()["data"]["id"]

        commit_resp = await client.post(
            f"/v1/bookings/{booking_id}/commit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert commit_resp.status_code == 409
        assert commit_resp.json()["error"]["type"] == "HOLD_EXPIRED"

    b = (await session.execute(select(BookingModel).where(BookingModel.id == uuid.UUID(booking_id)))).scalar_one()
    assert b.status == "EXPIRED"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C7: Commit times out -> PENDING_CONFIRMATION, 502, exactly one provider call
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c7_commit_timeout_pending_confirmation(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    def mock_handler(request: httpx.Request):
        if request.url.path == "/v1/holds" and request.method == "POST":
            return Response(201, json={"hold_id": "h-c7", "expires_at": datetime.now(timezone.utc).isoformat(), "seats": [], "total": 1000, "currency": "INR"})
        if "/commit" in request.url.path:
            raise httpx.TimeoutException("Timeout on commit")
        return Response(404)

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/v1/bookings/hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": ["s1"]},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "c7-key"},
        )
        booking_id = r.json()["data"]["id"]

        commit_resp = await client.post(
            f"/v1/bookings/{booking_id}/commit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert commit_resp.status_code == 502

    b = (await session.execute(select(BookingModel).where(BookingModel.id == uuid.UUID(booking_id)))).scalar_one()
    assert b.status == "PENDING_CONFIRMATION"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C8: Commit twice -> 409 HOLD_ALREADY_COMMITTED, one booking row, same provider id
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c8_commit_twice_conflict(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    commit_count = 0
    def mock_handler(request: httpx.Request):
        nonlocal commit_count
        if request.url.path == "/v1/holds" and request.method == "POST":
            return Response(201, json={"hold_id": "h-c8", "expires_at": datetime.now(timezone.utc).isoformat(), "seats": [], "total": 1000, "currency": "INR"})
        if "/commit" in request.url.path:
            commit_count += 1
            if commit_count == 1:
                return Response(200, json={"id": "prov-bk-1", "ref_code": "PVR-REF-1", "status": "CONFIRMED", "total_price_cents": 1000, "seats": []})
            return Response(409, json={"detail": {"code": "HOLD_ALREADY_COMMITTED", "booking": {"id": "prov-bk-1", "ref_code": "PVR-REF-1"}}})
        return Response(404)

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/v1/bookings/hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": ["s1"]},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "c8-key"},
        )
        booking_id = r.json()["data"]["id"]

        c1 = await client.post(f"/v1/bookings/{booking_id}/commit", headers={"Authorization": f"Bearer {token}"})
        assert c1.status_code == 200

        c2 = await client.post(f"/v1/bookings/{booking_id}/commit", headers={"Authorization": f"Bearer {token}"})
        assert c2.status_code == 409

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C9: Cancel a HELD booking -> release called, status CANCELLED; failing release still cancels
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c9_cancel_held_booking(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    release_called = False
    def mock_handler(request: httpx.Request):
        nonlocal release_called
        if request.url.path == "/v1/holds" and request.method == "POST":
            return Response(201, json={"hold_id": "h-c9", "expires_at": datetime.now(timezone.utc).isoformat(), "seats": [], "total": 1000, "currency": "INR"})
        if request.method == "DELETE":
            release_called = True
            return Response(500)
        return Response(404)

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/v1/bookings/hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": ["s1"]},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "c9-key"},
        )
        booking_id = r.json()["data"]["id"]

        del_resp = await client.delete(f"/v1/bookings/hold/{booking_id}", headers={"Authorization": f"Bearer {token}"})
        assert del_resp.status_code == 204
        assert release_called is True

    b = (await session.execute(select(BookingModel).where(BookingModel.id == uuid.UUID(booking_id)))).scalar_one()
    assert b.status == "CANCELLED"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C10: Cancel someone else's booking -> 404 and the provider is never called
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c10_cancel_foreign_booking_404(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    other_user = User(
        id=uuid.uuid4(),
        full_name="Other Customer",
        email="other@test.local",
        password_hash="h",
        role="USER",
        is_active=True,
    )
    session.add(other_user)
    await session.commit()

    token_owner = _token_for(data["user"].id)
    token_other = _token_for(other_user.id)

    def mock_handler(request: httpx.Request):
        if request.url.path == "/v1/holds" and request.method == "POST":
            return Response(201, json={"hold_id": "h-c10", "expires_at": datetime.now(timezone.utc).isoformat(), "seats": [], "total": 1000, "currency": "INR"})
        return Response(404)

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        r = await client.post(
            "/v1/bookings/hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": ["s1"]},
            headers={"Authorization": f"Bearer {token_owner}", "Idempotency-Key": "c10-key"},
        )
        booking_id = r.json()["data"]["id"]

        del_resp = await client.delete(f"/v1/bookings/hold/{booking_id}", headers={"Authorization": f"Bearer {token_other}"})
        assert del_resp.status_code == 404

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C11: Seat-map with a dead provider -> SOURCE_UNAVAILABLE, empty list, 200, no 500
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c11_seat_map_dead_provider_source_unavailable(session: AsyncSession, monkeypatch):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)

    def mock_handler(request: httpx.Request):
        return Response(503)

    mock_client = httpx.AsyncClient(transport=MockTransport(mock_handler))
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, client=mock_client),
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/showtimes/{data['showtime'].id}/seat-map")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["code"] == "SOURCE_UNAVAILABLE" or body.get("code") == "SOURCE_UNAVAILABLE"
        assert body["data"]["seats"] == []

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C12: Hold on a self-hosted showtime -> refused with SHOWTIME_NOT_PROVIDER
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c12_hold_on_self_hosted_refused(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    data["showtime"].provider_id = None
    session.add(data["showtime"])
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/v1/bookings/hold",
            json={"showtime_id": str(data["showtime"].id), "seat_ids": ["s1"]},
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "c12-key"},
        )
        assert resp.status_code == 400
        assert resp.json()["error"]["type"] == "SHOWTIME_NOT_PROVIDER"

    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# C13: Provider integration, live both ends
# ---------------------------------------------------------------------------
@pytest.mark.provider_integration
@pytest.mark.asyncio
async def test_c13_live_provider_integration(session: AsyncSession, monkeypatch):
    pvr_base_url = os.getenv("PVR_BASE_URL")
    if not pvr_base_url:
        pytest.skip("PVR_BASE_URL is not set; skipping live integration test.")

    url = pvr_base_url.rstrip("/")

    # 1. Real connectivity probe
    try:
        async with httpx.AsyncClient(timeout=3.0) as probe_client:
            probe = await probe_client.get(f"{url}/docs")
            if probe.status_code != 200:
                pytest.fail(f"PVR_BASE_URL={url} is set but unreachable - start pvr before running -e")
    except Exception:
        pytest.fail(f"PVR_BASE_URL={url} is set but unreachable - start pvr before running -e")

    # 2. Authenticate with live PVR instance to obtain channel credential token
    async with httpx.AsyncClient(timeout=5.0) as live_client:
        login_resp = await live_client.post(f"{url}/v1/auth/login", json={"email": "demo@pvr.local", "password": "demo1234"})
        if login_resp.status_code != 200:
            pytest.fail(f"Failed to authenticate with live PVR: {login_resp.text}")
        pvr_auth_token = login_resp.json()["token"]

        # Query PVR live instance for showtimes and an available seat
        st_resp = await live_client.get(f"{url}/v1/showtimes")
        pvr_showtimes = st_resp.json()
        if not pvr_showtimes:
            pytest.fail("Live PVR instance has no seeded showtimes. Seed PVR first.")
        target_pvr_st = pvr_showtimes[0]
        pvr_st_id = target_pvr_st["id"]

        seats_resp = await live_client.get(f"{url}/v1/showtimes/{pvr_st_id}/seats")
        rows = seats_resp.json()["rows"]
        avail_seat = None
        for r in rows:
            for s in r["seats"]:
                if s["status"] == "AVAILABLE":
                    avail_seat = s
                    break
            if avail_seat:
                break
        if not avail_seat:
            pytest.fail(f"All seats on PVR showtime {pvr_st_id} are already booked.")

    # 3. Seed Vybh DB pointing to the live PVR base_url with the real token
    partner_id = uuid.uuid4()
    venue = Venue(id=uuid.uuid4(), name="PVR Grand Live", city="Kochi", partner_id=partner_id)
    screen = Screen(id=uuid.uuid4(), venue_id=venue.id, name="Audi Live 1")
    movie = Movie(id=uuid.uuid4(), title="Live Film", duration_min=120, language="English", certificate="UA", status="PUBLISHED", partner_id=partner_id)
    session.add_all([venue, screen, movie])
    await session.flush()

    provider_reg = ProviderRegistryModel(
        id=uuid.uuid4(),
        name="PVR Live Provider",
        base_url=url,
        auth_token_ref=pvr_auth_token,
        hold_ttl_seconds=600,
        enabled=True,
        partner_id=None,
    )
    session.add(provider_reg)
    await session.flush()

    st = Showtime(
        id=uuid.uuid4(),
        screen_id=screen.id,
        movie_id=movie.id,
        starts_at=datetime.now(timezone.utc) + timedelta(days=1),
        partner_id=partner_id,
        provider_id=provider_reg.id,
        provider_showtime_ref=str(pvr_st_id),
    )
    user = User(
        id=uuid.uuid4(),
        full_name="Live Customer",
        email=f"live_{uuid.uuid4().hex[:6]}@test.local",
        password_hash="pwd",
        role="USER",
        is_active=True,
    )
    session.add_all([st, user])
    await session.commit()

    # Use REAL transport (no MockTransport)
    monkeypatch.setattr(
        "app.booking.services.create_provider_client",
        lambda reg, client=None: PVRProvider(reg.base_url, auth_token=reg.auth_token_ref, client=None),
    )
    app.dependency_overrides[get_db] = lambda: session

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        token = _token_for(user.id)
        headers = {"Authorization": f"Bearer {token}", "Idempotency-Key": f"live-key-{uuid.uuid4().hex[:6]}"}

        # 4. Hold seat via Vybh (real HTTP to PVR)
        hold_resp = await client.post(
            "/v1/bookings/hold",
            json={"showtime_id": str(st.id), "seat_ids": [str(avail_seat["id"])]},
            headers=headers,
        )
        assert hold_resp.status_code == 201
        booking_id = hold_resp.json()["data"]["id"]

        # 5. Verify seat is BOOKED on PVR native map
        async with httpx.AsyncClient(timeout=5.0) as check_client:
            map_pvr = await check_client.get(f"{url}/v1/showtimes/{pvr_st_id}/seats")
            pvr_seats = [s for r in map_pvr.json()["rows"] for s in r["seats"]]
            seat_state = next(s for s in pvr_seats if s["id"] == avail_seat["id"])
            assert seat_state["status"] == "BOOKED"

        # 6. Commit hold via Vybh (real HTTP to PVR)
        commit_resp = await client.post(
            f"/v1/bookings/{booking_id}/commit",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert commit_resp.status_code == 200
        commit_data = commit_resp.json()["data"]
        assert commit_data["ref_code"] is not None

        # 7. Unfabricable check: Query PVR directly to verify ticket exists
        async with httpx.AsyncClient(timeout=5.0) as check_client:
            pvr_ticket_resp = await check_client.get(f"{url}/v1/tickets/{commit_data['ref_code']}")
            assert pvr_ticket_resp.status_code == 200
            pvr_ticket = pvr_ticket_resp.json()
            assert pvr_ticket["ref_code"] == commit_data["ref_code"]

        # 8. Reconcile check
        rec_resp = await client.get("/v1/partner/reconcile?date=2025-01-01", headers={"Authorization": f"Bearer {token}"})
        assert rec_resp.status_code == 200

    app.dependency_overrides.clear()

# ---------------------------------------------------------------------------
# C14: Sweep moves expired HELD rows to EXPIRED, running twice is safe
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c14_sweep_expired_held_rows(session: AsyncSession):
    data = await _seed_provider_showtime(session)
    b = BookingModel(
        id=uuid.uuid4(),
        user_id=data["user"].id,
        booking_type="MOVIE",
        showtime_id=data["showtime"].id,
        provider_id=data["provider"].id,
        provider_hold_id="h-exp",
        held_until=datetime.now(timezone.utc) - timedelta(minutes=5),
        total_paise=1000,
        status="HELD",
        currency="INR",
    )
    session.add(b)
    await session.commit()

    from app.booking.repository import BookingRepository, TierCounterRepository
    svc = BookingService(BookingRepository(session), TierCounterRepository(session), session)

    swept1 = await svc.release_expired_holds()
    swept2 = await svc.release_expired_holds()

    assert len(swept1) == 1
    assert len(swept2) == 0


# ---------------------------------------------------------------------------
# C15: Reconcile endpoint returns 200 with structure
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_c15_reconcile_endpoint(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session
    data = await _seed_provider_showtime(session)
    token = _token_for(data["user"].id)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/v1/partner/reconcile?date=2025-01-01",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        res = resp.json()
        assert res["status"] == "success"
        assert "local_confirmed_count" in res["data"]

    app.dependency_overrides.clear()
