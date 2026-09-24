
import asyncio
import logging

from sqlalchemy import select

from app.movie.models import Movie
from app.movie.tmdb_client import search_and_get_rating
from app.core.database import AsyncSessionLocal
from app.shared.timeutil import utcnow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main() -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Movie).where(Movie.external_id.is_(None))
        )
        movies = result.scalars().all()
        logger.info("Backfilling %d movies", len(movies))

        ok = 0
        skipped = 0
        for m in movies:
            year = m.release_date.year if m.release_date else None
            match = await search_and_get_rating(m.title, year)
            if match is None:
                skipped += 1
                logger.info("SKIP %s (no TMDB match)", m.title)
                continue
            tmdb_id, rating = match
            m.external_id = tmdb_id
            m.external_rating = rating
            m.external_rating_fetched_at = utcnow()
            ok += 1
            logger.info("OK   %s -> %s (%.1f)", m.title, tmdb_id, rating)

        await session.commit()
        logger.info("Done. matched=%d skipped=%d", ok, skipped)


if __name__ == "__main__":
    asyncio.run(main())