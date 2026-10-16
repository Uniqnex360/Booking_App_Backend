"""
Seed active future showtimes for all 6 restored movies across all 3 cities (Bangalore, Chennai, Kochi)
so that they appear consistently in the movie listings and details.
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Add backend root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.movie.models import Movie, Showtime, Venue, Screen
from app.partner.models import PartnerORM
from app.providers.registry import ProviderRegistryModel
from app.shared.timeutil import utcnow

TITLES_TO_POPULATE = [
    "I Am Game",
    "Kingdom",
    "Last Whistle",
    "The Final Whistle",
    "Jailer 2",
    "Avengers: Endgame Encore",
]

DAILY_HOURS = [(11, 0), (14, 30), (18, 0), (21, 15)]

async def seed_showtimes():
    print("--- Seeding showtimes for all 6 restored titles across all cities ---")
    async with AsyncSessionLocal() as session:
        # Get partner
        partner_res = await session.execute(select(PartnerORM).limit(1))
        partner = partner_res.scalar_one_or_none()
        partner_id = partner.id if partner else uuid.uuid4()

        movies_res = await session.execute(
            select(Movie).where(Movie.title.in_(TITLES_TO_POPULATE))
        )
        movies = {m.title: m for m in movies_res.scalars().all()}

        # Make sure they are all published
        for m in movies.values():
            m.status = "PUBLISHED"

        screens_res = await session.execute(
            select(Screen, Venue).join(Venue, Venue.id == Screen.venue_id)
        )
        screens_by_city: dict[str, list[Screen]] = {}
        for s, v in screens_res.all():
            if v and v.city:
                screens_by_city.setdefault(v.city, []).append(s)

        now_utc = utcnow()
        existing_res = await session.execute(
            select(Showtime.screen_id, Showtime.starts_at).where(Showtime.starts_at > now_utc)
        )
        existing_slots = set((r[0], r[1]) for r in existing_res.all())

        tz_kolkata = ZoneInfo("Asia/Kolkata")
        today_kolkata = now_utc.astimezone(tz_kolkata).date()

        new_showtimes = []

        for m_idx, title in enumerate(TITLES_TO_POPULATE):
            m = movies.get(title)
            if not m:
                print(f"Movie {title} not found in DB!")
                continue

            for city in ["Kochi", "Bangalore", "Chennai"]:
                c_screens = screens_by_city.get(city, [])
                if not c_screens:
                    continue

                # Assign 2 dedicated screens in each city
                s1 = c_screens[(m_idx * 2) % len(c_screens)]
                s2 = c_screens[(m_idx * 2 + 1) % len(c_screens)]

                for screen in [s1, s2]:
                    for day_idx in range(7):
                        day_dt = today_kolkata + timedelta(days=day_idx)
                        for hr, mn in DAILY_HOURS:
                            local_dt = datetime.combine(day_dt, time(hr, mn), tzinfo=tz_kolkata)
                            utc_dt = local_dt.astimezone(timezone.utc)

                            if utc_dt <= now_utc:
                                continue
                            if (screen.id, utc_dt) in existing_slots:
                                continue

                            existing_slots.add((screen.id, utc_dt))
                            new_showtimes.append(
                                Showtime(
                                    id=uuid.uuid4(),
                                    screen_id=screen.id,
                                    movie_id=m.id,
                                    starts_at=utc_dt,
                                    language=m.language or "English",
                                    format="2D",
                                    status="ACTIVE",
                                    partner_id=partner_id,
                                )
                            )

        if new_showtimes:
            session.add_all(new_showtimes)
            print(f"Added {len(new_showtimes)} showtimes for restored movies across Kochi, Bangalore, Chennai.")
        else:
            print("Showtimes already present.")

        await session.commit()
        print("Done!")

if __name__ == "__main__":
    asyncio.run(seed_showtimes())

