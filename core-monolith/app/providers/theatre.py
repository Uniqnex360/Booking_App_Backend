"""
PVR Theatre Provider Adapter implementing ITheatreProvider with httpx.AsyncClient.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone
from typing import Any
import httpx

from app.providers.base import (
    HoldAlreadyCommitted,
    HoldExpiredRemote,
    ITheatreProvider,
    ProviderContractError,
    ProviderHold,
    ProviderHoldState,
    ProviderHeldSeat,
    ProviderSeat,
    ProviderSeatMap,
    ProviderShowtime,
    ProviderTicket,
    ProviderTicketSeat,
    ProviderUnavailable,
    SeatUnavailableRemote,
)

logger = logging.getLogger(__name__)


def _extract_price(item: dict, fallback: int = 0) -> int:
    if not isinstance(item, dict):
        return fallback
    for k, v in item.items():
        if isinstance(v, (int, float)) and v > 0:
            k_lower = k.lower()
            if any(term in k_lower for term in ("price", "total", "quote", "amount", "cost")):
                return int(v)
    return fallback


class PVRProvider(ITheatreProvider):
    def __init__(
        self,
        base_url: str,
        auth_token: str | None = None,
        timeout_seconds: float = 45.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth_token = auth_token
        self._timeout = timeout_seconds
        self._client = client

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is not None:
            return self._client
        headers = {}
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return httpx.AsyncClient(
            base_url=self._base_url,
            headers=headers,
            timeout=self._timeout,
        )

    def _headers(self) -> dict[str, str]:
        if self._auth_token:
            return {"Authorization": f"Bearer {self._auth_token}"}
        return {}

    async def _request_with_retry(
        self, method: str, path: str, **kwargs
    ) -> httpx.Response:
        client = self._get_client()
        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                return await client.request(
                    method,
                    f"{self._base_url}{path}",
                    headers=self._headers(),
                    timeout=self._timeout,
                    **kwargs,
                )
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(20.0)
                    continue
                raise ProviderUnavailable(
                    f"PVR {method} {path} failed after retry: {last_exc}"
                ) from last_exc
        raise ProviderUnavailable(f"PVR {method} {path} unreachable: {last_exc}")

    async def _get_with_retry(self, path: str, params: dict | None = None) -> httpx.Response:
        client = self._get_client()
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                resp = await client.get(
                    f"{self._base_url}{path}", params=params, headers=self._headers(), timeout=self._timeout
                )
                if resp.status_code >= 500:
                    if attempt < 2:
                        await asyncio.sleep(20.0 if attempt == 0 else 40.0)
                        continue
                    raise ProviderUnavailable(f"PVR upstream 5xx on GET {path}: {resp.status_code}")
                return resp
            except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as exc:
                last_exc = exc
                if attempt < 2:
                    await asyncio.sleep(20.0 if attempt == 0 else 40.0)
                    continue
        raise ProviderUnavailable(f"PVR upstream unreachable on GET {path}: {last_exc}")
    async def cancel_booking(self, provider_booking_id: str) -> None:
        resp = await self._request_with_retry(
            "POST", f"/v1/bookings/{provider_booking_id}/cancel"
        )
        if resp.status_code not in (200, 204, 404) and resp.status_code >= 500:
            raise ProviderUnavailable(
                f"PVR 5xx on cancel booking {provider_booking_id}: {resp.status_code}"
            )
    async def list_showtimes(self, target_date: date) -> list[ProviderShowtime]:
        resp = await self._get_with_retry(
            "/v1/showtimes", params={"date": target_date.isoformat()}
        )
        if resp.status_code != 200:
            raise ProviderContractError(
                f"Unexpected status {resp.status_code} listing showtimes", resp.text
            )
        try:
            data = resp.json()
            results: list[ProviderShowtime] = []
            for st in data:
                starts_at = datetime.fromisoformat(st["starts_at"].replace("Z", "+00:00"))
                if starts_at.tzinfo is None:
                    starts_at = starts_at.replace(tzinfo=timezone.utc)
                results.append(
                    ProviderShowtime(
                        provider_showtime_ref=str(st["id"]),
                        movie_title=st["movie_title"],
                        screen_name=st["screen_name"],
                        cinema_name=st["cinema_name"],
                        starts_at=starts_at,
                        language=st.get("language"),
                        certificate=st.get("certificate"),
                        duration_min=st.get("duration_min"),
                    )
                )
            return results
        except Exception as exc:
            raise ProviderContractError(
                f"Failed to parse showtimes list: {exc}", resp.text
            ) from exc

    async def seat_map(self, showtime_ref: str) -> ProviderSeatMap:
        resp = await self._get_with_retry(f"/v1/showtimes/{showtime_ref}/seats")
        if resp.status_code == 404:
            raise ProviderContractError(f"Showtime {showtime_ref} not found on provider", resp.text)
        if resp.status_code != 200:
            raise ProviderContractError(
                f"Unexpected status {resp.status_code} fetching seat map", resp.text
            )
        try:
            data = resp.json()
            seats: list[ProviderSeat] = []
            for row in data.get("rows", []):
                row_label = row.get("label", "")
                row_price = _extract_price(row, 0)
                for s in row.get("seats", []):
                    price_paise = _extract_price(s, row_price)
                    is_avail = s.get("status") == "AVAILABLE"
                    seats.append(
                        ProviderSeat(
                            seat_ref=str(s["id"]),
                            row_label=row_label,
                            seat_number=s.get("number", 0),
                            seat_code=s.get("code", ""),
                            price_paise=price_paise,
                            is_available=is_avail,
                        )
                    )
            starts_at = datetime.fromisoformat(data["starts_at"].replace("Z", "+00:00"))
            if starts_at.tzinfo is None:
                starts_at = starts_at.replace(tzinfo=timezone.utc)
            return ProviderSeatMap(
                showtime_ref=str(data["showtime_id"]),
                movie_title=data.get("movie_title", ""),
                screen_name=data.get("screen_name", ""),
                cinema_name=data.get("cinema_name", ""),
                starts_at=starts_at,
                seats=seats,
                fetched_at=datetime.now(timezone.utc),
            )
        except Exception as exc:
            raise ProviderContractError(f"Failed to parse seat map: {exc}", resp.text) from exc

    async def hold(
        self,
        showtime_ref: str,
        seat_refs: list[str],
        idem_key: str,
        end_user_ref: str | None,
    ) -> ProviderHold:
        client = self._get_client()
        payload = {
            "showtime_id": showtime_ref,
            "seat_ids": seat_refs,
            "idempotency_key": idem_key,
            "end_user_ref": end_user_ref,
        }
        resp = await self._request_with_retry("POST", "/v1/holds", json=payload)

        if resp.status_code == 201:
            try:
                data = resp.json()
                expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
                if expires_at.tzinfo is None:
                    expires_at = expires_at.replace(tzinfo=timezone.utc)
                held_seats = [
                    ProviderHeldSeat(
                        seat_ref=str(s["seat_id"]),
                        seat_code=s.get("code", ""),
                        price_paise=_extract_price(s, 0),
                    )
                    for s in data.get("seats", [])
                ]
                total_paise = _extract_price(data, 0)
                return ProviderHold(
                    hold_id=str(data["hold_id"]),
                    expires_at=expires_at,
                    seats=held_seats,
                    total_paise=total_paise,
                    currency=data.get("currency", "INR"),
                )
            except Exception as exc:
                raise ProviderContractError(f"Failed to parse hold 201 response: {exc}", resp.text) from exc

        if resp.status_code == 409:
            try:
                data = resp.json()
                seats = data.get("detail", {}).get("seats", [])
                raise SeatUnavailableRemote([str(s) for s in seats])
            except SeatUnavailableRemote:
                raise
            except Exception:
                raise SeatUnavailableRemote(seat_refs)

        if resp.status_code >= 500:
            raise ProviderUnavailable(f"PVR 5xx on hold: {resp.status_code}")

        raise ProviderContractError(f"Unexpected status {resp.status_code} on hold", resp.text)

    async def commit(
        self, hold_id: str, payment_ref: str | None = None
    ) -> ProviderTicket:
        client = self._get_client()
        payload = {"payment_ref": payment_ref}
        resp = await self._request_with_retry(
            "POST", f"/v1/holds/{hold_id}/commit", json=payload
        )

        if resp.status_code == 200:
            try:
                data = resp.json()
                created_at = datetime.fromisoformat(str(data.get("created_at", datetime.now(timezone.utc).isoformat())).replace("Z", "+00:00"))
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=timezone.utc)
                seats = [
                    ProviderTicketSeat(
                        seat_ref=str(s.get("seat_id", "")),
                        seat_code=s.get("code", ""),
                        price_paise=_extract_price(s, 0),
                    )
                    for s in data.get("seats", [])
                ]
                total_paise = _extract_price(data, 0)
                return ProviderTicket(
                    booking_id=str(data.get("id", data.get("booking_id", ""))),
                    ref_code=data.get("ref_code", ""),
                    status=data.get("status", "CONFIRMED"),
                    total_paise=total_paise,
                    currency=data.get("currency", "INR"),
                    seats=seats,
                    created_at=created_at,
                    barcode=data.get("barcode", f"BARCODE-{data.get('ref_code', '')}"),
                )
            except Exception as exc:
                raise ProviderContractError(f"Failed to parse commit 200 response: {exc}", resp.text) from exc

        if resp.status_code == 410:
            raise HoldExpiredRemote(f"Hold {hold_id} expired on provider")

        if resp.status_code == 409:
            try:
                detail = resp.json().get("detail", {})
                booking_info = detail.get("booking", {})
                b_ref = booking_info.get("ref_code")
                b_id = booking_info.get("id")
                raise HoldAlreadyCommitted(booking_ref=b_ref, booking_id=str(b_id) if b_id else None)
            except HoldAlreadyCommitted:
                raise
            except Exception:
                raise HoldAlreadyCommitted()

        if resp.status_code >= 500:
            raise ProviderUnavailable(f"PVR 5xx on commit: {resp.status_code}")

        raise ProviderContractError(f"Unexpected status {resp.status_code} on commit", resp.text)

    async def release(self, hold_id: str) -> None:
        client = self._get_client()
        resp = await self._request_with_retry("DELETE", f"/v1/holds/{hold_id}")
        if resp.status_code not in (200, 204, 404) and resp.status_code >= 500:
            raise ProviderUnavailable(f"PVR 5xx on release: {resp.status_code}")

    async def hold_state(self, hold_id: str) -> ProviderHoldState:
        resp = await self._get_with_retry(f"/v1/holds/{hold_id}")
        if resp.status_code != 200:
            raise ProviderContractError(
                f"Unexpected status {resp.status_code} getting hold state", resp.text
            )
        try:
            data = resp.json()
            expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            seats = [
                ProviderHeldSeat(
                    seat_ref=str(s["seat_id"]),
                    seat_code=s.get("code", ""),
                    price_paise=_extract_price(s, 0),
                )
                for s in data.get("seats", [])
            ]
            return ProviderHoldState(
                hold_id=str(data["hold_id"]),
                showtime_ref=str(data["showtime_id"]),
                status=data["status"],
                expires_at=expires_at,
                quote_total_paise=_extract_price(data, 0),
                currency=data.get("currency", "INR"),
                seats=seats,
            )
        except Exception as exc:
            raise ProviderContractError(f"Failed to parse hold state: {exc}", resp.text) from exc

    async def bookings_between(
        self, start: datetime, end: datetime
    ) -> list[ProviderTicket]:
        return []
