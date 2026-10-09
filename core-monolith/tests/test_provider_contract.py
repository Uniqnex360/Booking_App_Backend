# tests/test_provider_contract.py
"""
Contract test: PVRProvider speaks to a chain-app that implements the
7-endpoint contract. Mounts a mock chain-app over ASGITransport so no
network is needed. If this passes, a chain-app that satisfies the mock
satisfies core-monolith's provider client.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from app.providers.theatre import PVRProvider


@pytest.fixture
def mock_chain_app() -> FastAPI:
    app = FastAPI()
    state: dict = {"holds": {}, "bookings": {}}

    @app.get("/v1/showtimes")
    async def list_showtimes(date: str | None = None):
        return [
            {
                "id": "sh-1",
                "movie_title": "Test Movie",
                "screen_name": "Screen 1",
                "cinema_name": "Test Cinema",
                "starts_at": "2026-09-21T10:00:00Z",
                "language": "English",
                "certificate": "UA",
                "duration_min": 120,
            }
        ]

    @app.get("/v1/showtimes/{ref}/seats")
    async def seat_map(ref: str):
        if ref != "sh-1":
            raise HTTPException(404, "not found")
        return {
            "showtime_id": ref,
            "movie_title": "Test Movie",
            "screen_name": "Screen 1",
            "cinema_name": "Test Cinema",
            "starts_at": "2026-09-21T10:00:00Z",
            "rows": [
                {
                    "label": "A",
                    "price_paise": 19000,
                    "seats": [
                        {"id": "s1", "number": 1, "code": "A1",
                         "status": "AVAILABLE", "price_paise": 19000},
                        {"id": "s2", "number": 2, "code": "A2",
                         "status": "AVAILABLE", "price_paise": 19000},
                    ],
                }
            ],
        }

    @app.post("/v1/holds", status_code=201)
    async def hold(body: dict):
        hold_id = "h-1"
        state["holds"][hold_id] = {
            "hold_id": hold_id,
            "showtime_id": body["showtime_id"],
            "expires_at": "2026-09-21T11:00:00Z",
            "seats": [
                {"seat_id": sid, "code": f"A{sid[-1]}", "price_paise": 19000}
                for sid in body["seat_ids"]
            ],
            "total_paise": 19000 * len(body["seat_ids"]),
            "currency": "INR",
            "status": "HELD",
        }
        return state["holds"][hold_id]

    @app.post("/v1/holds/{hold_id}/commit")
    async def commit(hold_id: str, body: dict | None = None):
        if hold_id not in state["holds"]:
            raise HTTPException(404, "hold not found")
        h = state["holds"][hold_id]
        return {
            "id": "b-1",
            "created_at": "2026-09-21T10:05:00Z",
            "ref_code": "TEST-REF-1",
            "status": "CONFIRMED",
            "total_paise": h["total_paise"],
            "currency": "INR",
            "seats": h["seats"],
        }

    @app.delete("/v1/holds/{hold_id}", status_code=204)
    async def release(hold_id: str):
        state["holds"].pop(hold_id, None)
        return None

    @app.get("/v1/holds/{hold_id}")
    async def hold_state(hold_id: str):
        if hold_id not in state["holds"]:
            raise HTTPException(404, "hold not found")
        return state["holds"][hold_id]

    return app


@pytest.mark.asyncio
async def test_pvr_client_speaks_chain_contract(mock_chain_app: FastAPI):
    transport = ASGITransport(app=mock_chain_app)
    async with AsyncClient(transport=transport, base_url="http://chain.test") as http:
        provider = PVRProvider(base_url="http://chain.test", client=http)

        # list_showtimes
        shows = await provider.list_showtimes(date(2026, 9, 21))
        assert len(shows) == 1
        assert shows[0].movie_title == "Test Movie"
        assert shows[0].provider_showtime_ref == "sh-1"

        # seat_map
        sm = await provider.seat_map(shows[0].provider_showtime_ref)
        assert sm.cinema_name == "Test Cinema"
        assert sm.showtime_ref == "sh-1"
        assert len(sm.seats) == 2
        assert sm.seats[0].seat_ref == "s1"
        assert sm.seats[0].seat_code == "A1"
        assert sm.seats[0].is_available is True

        # hold
        hold = await provider.hold(
            showtime_ref="sh-1",
            seat_refs=["s1", "s2"],
            idem_key="key-1",
            end_user_ref="user-1",
        )
        assert hold.hold_id == "h-1"
        assert hold.total_paise == 38000
        assert len(hold.seats) == 2

        # commit
        ticket = await provider.commit(hold.hold_id)
        assert ticket.ref_code == "TEST-REF-1"
        assert ticket.status == "CONFIRMED"

        # release — should not raise
        await provider.release("nonexistent-hold")

        # hold_state on a fresh hold
        hold2 = await provider.hold(
            showtime_ref="sh-1",
            seat_refs=["s1"],
            idem_key="key-2",
            end_user_ref="user-1",
        )
        state = await provider.hold_state(hold2.hold_id)
        assert state.status == "HELD"
        assert state.showtime_ref == "sh-1"
from app.providers.registry import (
    ProviderRegistryModel,
    create_provider_client,
)


def test_create_provider_client_dispatches_on_adapter():
    row_pvr = ProviderRegistryModel(
        name="PVR",
        base_url="http://pvr.example",
        hold_ttl_seconds=600,
        adapter="pvr",
    )
    assert create_provider_client(row_pvr) is not None

    row_ags = ProviderRegistryModel(
        name="AGS",
        base_url="http://ags.example",
        hold_ttl_seconds=600,
        adapter="http",
    )
    client_ags = create_provider_client(row_ags)
    assert client_ags is not None
    assert client_ags._base_url == "http://ags.example"

    row_bad = ProviderRegistryModel(
        name="Bad",
        base_url="http://bad.example",
        hold_ttl_seconds=600,
        adapter="soap",
    )
    import pytest as _pytest
    with _pytest.raises(ValueError, match="Unknown provider adapter"):
        create_provider_client(row_bad)