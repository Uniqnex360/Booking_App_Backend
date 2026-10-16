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

    def _release_year(item: dict) -> Optional[int]:
        rd = item.get("release_date") or ""
        if len(rd) >= 4 and rd[:4].isdigit():
            return int(rd[:4])
        return None

    def _pick(results: list[dict]) -> Optional[dict]:
        if not year:
            return results[0] if results else None
        for r in results:
            ry = _release_year(r)
            if ry is not None and abs(ry - year) <= 1:
                return r
        return None

    query = {"query": title.strip()}

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            headers = _headers()
            if year:
                for y in (year, year - 1, year + 1):
                    try:
                        r = await client.get(
                            f"{TMDB_BASE}/search/movie", params={**query, "year": y}, headers=headers
                        )
                        if r.status_code == 200:
                            results = r.json().get("results") or []
                            best = _pick(results)
                            if best:
                                return _finalize(best)
                    except Exception as e:
                        logger.debug("TMDB query year %s failed: %s", y, e)
                return None

            r = await client.get(
                f"{TMDB_BASE}/search/movie", params=query, headers=headers
            )
            if r.status_code == 200:
                results = r.json().get("results") or []
                best = _pick(results)
                return _finalize(best) if best else None
            return None
    except Exception as e:
        logger.warning("TMDB client error for %r: %s", title, e)
        return None


def _finalize(best: dict) -> Optional[tuple[str, float]]:
    rating = float(best.get("vote_average") or 0.0)
    tmdb_id = best.get("id")
    if not tmdb_id or rating < 0.1:
        return None
    return str(tmdb_id), round(rating, 1)