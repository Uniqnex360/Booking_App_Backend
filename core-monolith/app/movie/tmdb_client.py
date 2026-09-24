import logging
from typing import Optional
import os
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

TMDB_BASE = settings.TMDB_BASE

def _headers() -> dict:
    if not settings.TMDB_BEARER_TOKEN:
        raise RuntimeError("TMDB_BEARER_TOKEN not configured")
    return {
        "Authorization": f"Bearer {settings.TMDB_BEARER_TOKEN}",
        "Accept": "application/json",
    }
async def search_and_get_rating(
    title: str, year: Optional[int] = None
) -> Optional[tuple[str, float]]:
    
    if not title or not title.strip():
        return None

    async def _search(params: dict) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                r = await client.get(
                    f"{TMDB_BASE}/search/movie", params=params, headers=_headers()
                )
                r.raise_for_status()
                data = r.json()
        except Exception as e:
            logger.warning("TMDB search failed for %r: %s", title, e)
            return []
        return data.get("results") or []

    def _release_year(item: dict) -> Optional[int]:
        rd = item.get("release_date") or ""
        if len(rd) >= 4 and rd[:4].isdigit():
            return int(rd[:4])
        return None

    def _pick(results: list[dict]) -> Optional[dict]:
        if not year:
            return results[0] if results else None
        # Prefer results whose release year is within ±1 of target.
        for r in results:
            ry = _release_year(r)
            if ry is not None and abs(ry - year) <= 1:
                return r
        return None

    query = {"query": title.strip()}

    if year:
        for y in (year, year - 1, year + 1):
            results = await _search({**query, "year": y})
            best = _pick(results)
            if best:
                return _finalize(best)
        return None

    results = await _search(query)
    best = _pick(results)
    return _finalize(best) if best else None


def _finalize(best: dict) -> Optional[tuple[str, float]]:
    rating = float(best.get("vote_average") or 0.0)
    tmdb_id = best.get("id")
    if not tmdb_id or rating < 0.1:
        return None
    return str(tmdb_id), round(rating, 1)