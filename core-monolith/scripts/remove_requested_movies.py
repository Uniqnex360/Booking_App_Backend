"""
Script to unpublish (status='DRAFT') and cancel future showtimes for the movies requested by user:
- Vettaiyan
- The Greatest of All Time (GOAT)
- Lubber Pandhu
- Kalki 2898 AD
- Devara: Part 1
- Meiyazhagan
- Bhool Bhulaiyaa 3
- Stree 2: Sarkate Ka Aatank (and Stree 2)
- Lucky Baskhar
- Pushpa 2: The Rule
- Vidaamuyarchi
- Bougainvillea
- Kishkindha Kaandam
- Jigra
- Game Changer
- Kanguva
- Dragon
- Baby John
- Sikandar
- Barroz
- L2: Empuraan
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from app.core.database import AsyncSessionLocal
from app.movie.models import Movie, Showtime
from app.providers.registry import ProviderRegistryModel
from app.shared.timeutil import utcnow

MOVIES_TO_REMOVE = [
    "Vettaiyan",
    "The Greatest of All Time (GOAT)",
    "Lubber Pandhu",
    "Kalki 2898 AD",
    "Devara: Part 1",
    "Meiyazhagan",
    "Bhool Bhulaiyaa 3",
    "Stree 2: Sarkate Ka Aatank",
    "Stree 2",
    "Lucky Baskhar",
    "Pushpa 2: The Rule",
    "Vidaamuyarchi",
    "Bougainvillea",
    "Kishkindha Kaandam",
    "Jigra",
    "Game Changer",
    "Kanguva",
    "Dragon",
    "Baby John",
    "Sikandar",
    "Barroz",
    "L2: Empuraan",
]

async def remove_movies():
    print(f"--- Removing {len(MOVIES_TO_REMOVE)} movies from active catalog ---")
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(Movie).where(Movie.title.in_(MOVIES_TO_REMOVE))
        )
        movies = res.scalars().all()
        now = utcnow()

        removed_count = 0
        for m in movies:
            m.status = "DRAFT"
            removed_count += 1
            print(f"Removed (DRAFT): {m.title}")

            # Cancel future showtimes for this movie
            await session.execute(
                update(Showtime)
                .where((Showtime.movie_id == m.id) & (Showtime.starts_at > now))
                .values(status="CANCELLED")
            )

        await session.commit()
        print(f"\nSuccessfully unpublished {removed_count} movies from active public catalog!")

if __name__ == "__main__":
    asyncio.run(remove_movies())
