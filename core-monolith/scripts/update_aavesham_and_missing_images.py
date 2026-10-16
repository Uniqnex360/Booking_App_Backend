"""
Update Aavesham and any remaining catalog movies with verified, official, high-resolution poster and banner URLs.
"""

import asyncio
import os
import sys
from pathlib import Path

# Add backend root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.movie.models import Movie
from app.providers.registry import ProviderRegistryModel

MOVIE_IMAGE_UPDATES = {
    "Aavesham": {
        "poster": "https://image.tmdb.org/t/p/w500/k5RWPaNjgRcNvGoawYaQHQwyctI.jpg",
        "banner": "https://image.tmdb.org/t/p/original/sJa3WaCx3IyU7zkudlMs7lb13gt.jpg",
    },
    "Martin": {
        "poster": "https://image.tmdb.org/t/p/w500/rmCJCFrEwPC0u0Y1smihwDo4Cf1.jpg",
        "banner": "https://image.tmdb.org/t/p/original/mVtc8uLWtqwqorHl8UkhtxWNUJo.jpg",
    },
    "ARM: Ajayante Randam Moshanam": {
        "poster": "https://image.tmdb.org/t/p/w500/OClpEeRlHK3DrFO7QtWXtpDIOK.jpg",
        "banner": "https://image.tmdb.org/t/p/original/4VMaNlyZg7HNCTwkAIdi39j8463.jpg",
    },
    "The Wild Robot": {
        "poster": "https://image.tmdb.org/t/p/w500/wTnV3PCVW5O92JMrFvvrRcV39RU.jpg",
        "banner": "https://image.tmdb.org/t/p/original/1pmXyN3sKeYoUhu5VBZiDU4BX21.jpg",
    },
    "Deadpool & Wolverine": {
        "poster": "https://image.tmdb.org/t/p/w500/8cdWjvZQUExUUTzyp4t6EDMubfO.jpg",
        "banner": "https://image.tmdb.org/t/p/original/by8z9Fe8y7p4jo2YlW2SZDnptyT.jpg",
    },
    "Vaazha": {
        "poster": "https://image.tmdb.org/t/p/w500/6SFL0Z5x4FQTNYoDCp6SbbyydQm.jpg",
        "banner": "https://image.tmdb.org/t/p/original/65vGOUKdIycwaXdXbzdN1ns8jaL.jpg",
    },
    "Max": {
        "poster": "https://upload.wikimedia.org/wikipedia/en/4/4c/Max_Kannada_film_poster.jpg",
        "banner": "https://upload.wikimedia.org/wikipedia/en/4/4c/Max_Kannada_film_poster.jpg",
    },
}

async def update_images():
    print("--- Updating Aavesham and other catalog movies with authentic images ---")
    async with AsyncSessionLocal() as session:
        for title, img in MOVIE_IMAGE_UPDATES.items():
            res = await session.execute(select(Movie).where(Movie.title == title))
            m = res.scalar_one_or_none()
            if m:
                m.poster_url = img["poster"]
                m.banner_url = img["banner"]
                print(f"Updated {title}:")
                print(f"  Poster: {img['poster']}")
                print(f"  Banner: {img['banner']}")
            else:
                print(f"Movie {title} not found in DB!")

        await session.commit()
        print("\nAll image updates committed successfully!")

if __name__ == "__main__":
    asyncio.run(update_images())

