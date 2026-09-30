import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio


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