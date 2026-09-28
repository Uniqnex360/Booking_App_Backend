import asyncio
import os
import sys
import uuid
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
from app.movie.models import Movie, Showtime, Screen, Venue, ScreenRow, Seat
from app.partner.models import PartnerORM
from app.shared.providers.registry import ProviderRegistryModel
from sqlalchemy import select, func

ROW_SPECS = [
    ("A", 12, 45000, "COUPLE RECLINER"),
    ("B", 12, 45000, "COUPLE RECLINER"),
    ("C", 12, 45000, "COUPLE RECLINER"),
    ("D", 10, 50000, "COUPLE LOUNGER"),
]

PVR_DB_PATH = "/home/lexicon/Documents/Harisankar/Projects/pvr-app/backend/pvr.db"

async def main():
    print("Seeding Screen 4 (Couple Recliners) into Core Monolith Postgres DB...")
    async with AsyncSessionLocal() as session:
        # 1. Partner
        partner_res = await session.execute(
            select(PartnerORM).where(PartnerORM.business_name == "PVR Cinemas Ltd")
        )
        partner = partner_res.scalar_one_or_none()
        if not partner:
            partner_res = await session.execute(select(PartnerORM).limit(1))
            partner = partner_res.scalar_one_or_none()
        if not partner:
            print("ERROR: No partner found!")
            return

        # 2. Provider
        provider_res = await session.execute(
            select(ProviderRegistryModel).where(ProviderRegistryModel.name.ilike("%pvr%"))
        )
        provider = provider_res.scalar_one_or_none()
        if not provider:
            print("ERROR: No PVR provider found!")
            return

        # 3. Venues
        venues_res = await session.execute(
            select(Venue).where(Venue.name.ilike("%pvr%"))
        )
        venues = venues_res.scalars().all()
        print(f"Found {len(venues)} PVR venues.")

        screens_by_venue = {}
        for venue in venues:
            # Check or create Screen 4
            screen_res = await session.execute(
                select(Screen).where(
                    Screen.venue_id == venue.id,
                    Screen.name == "Screen 4 (Couple Recliners)"
                )
            )
            screen = screen_res.scalar_one_or_none()
            if not screen:
                screen = Screen(
                    id=uuid.uuid4(),
                    venue_id=venue.id,
                    name="Screen 4 (Couple Recliners)",
                    total_seats=46,
                )
                session.add(screen)
                await session.flush()
                print(f"Created screen '{screen.name}' for {venue.name}")
            screens_by_venue[venue.name] = screen

            # Ensure rows and seats
            for label, count, price, sec in ROW_SPECS:
                row_res = await session.execute(
                    select(ScreenRow).where(
                        ScreenRow.screen_id == screen.id,
                        ScreenRow.label == label
                    )
                )
                row = row_res.scalar_one_or_none()
                if not row:
                    row = ScreenRow(
                        id=uuid.uuid4(),
                        screen_id=screen.id,
                        label=label,
                        seat_count=count,
                        price_paise=price,
                        section=sec,
                    )
                    session.add(row)
                    await session.flush()

                # Ensure seats
                existing_seats_count = (await session.execute(
                    select(func.count()).select_from(Seat).where(Seat.row_id == row.id)
                )).scalar() or 0

                if existing_seats_count == 0:
                    for num in range(1, count + 1):
                        seat = Seat(
                            id=uuid.uuid4(),
                            row_id=row.id,
                            number=num,
                            x=num,
                            code=f"{label}{num:02d}",
                            label=f"{label}{num}",
                        )
                        session.add(seat)
                    await session.flush()

        await session.commit()
        print("Screen 4 rows and seats ensured for all PVR venues.")

        # 4. Fetch movies from Monolith DB
        all_movies_res = await session.execute(select(Movie))
        all_movies = all_movies_res.scalars().all()
        movies_by_title = {m.title.lower(): m for m in all_movies}

        # 5. Read showtimes from pvr.db
        pconn = sqlite3.connect(PVR_DB_PATH)
        pc = pconn.cursor()
        pc.execute('''
            SELECT st.id, m.title, c.name, st.starts_at, m.language
            FROM showtimes st
            JOIN screens s ON st.screen_id = s.id
            JOIN cinemas c ON s.cinema_id = c.id
            JOIN movies m ON st.movie_id = m.id
            WHERE s.name LIKE '%Couple%'
        ''')
        pvr_showtimes = pc.fetchall()
        pconn.close()
        print(f"Read {len(pvr_showtimes)} couple showtimes from pvr.db")

        now = datetime.now(timezone.utc)
        all_refs = [st[0] for st in pvr_showtimes]
        existing_showtimes_res = await session.execute(
            select(Showtime).where(Showtime.provider_showtime_ref.in_(all_refs))
        )
        existing_by_ref = {s.provider_showtime_ref: s for s in existing_showtimes_res.scalars().all()}

        new_showtimes = []
        for pvr_st_id, movie_title, cinema_name, starts_at_str, lang in pvr_showtimes:
            movie = movies_by_title.get(movie_title.lower())
            if not movie:
                for m_title, m_obj in movies_by_title.items():
                    if movie_title.lower() in m_title or m_title in movie_title.lower():
                        movie = m_obj
                        break
            if not movie:
                continue

            screen = screens_by_venue.get(cinema_name)
            if not screen:
                continue

            # Parse datetime
            clean_starts = starts_at_str.replace("Z", "+00:00")
            if "." in clean_starts:
                clean_starts = clean_starts.split(".")[0]
            starts_at_dt = datetime.fromisoformat(clean_starts)
            if starts_at_dt.tzinfo is None:
                starts_at_dt = starts_at_dt.replace(tzinfo=timezone.utc)

            existing_st = existing_by_ref.get(pvr_st_id)
            if not existing_st:
                new_st = Showtime(
                    id=uuid.uuid4(),
                    screen_id=screen.id,
                    movie_id=movie.id,
                    starts_at=starts_at_dt,
                    language=movie.language or lang or "Malayalam",
                    format="COUPLE RECLINER",
                    status="ACTIVE",
                    partner_id=partner.id,
                    provider_id=provider.id,
                    provider_showtime_ref=pvr_st_id,
                )
                new_showtimes.append(new_st)
            else:
                existing_st.screen_id = screen.id
                existing_st.provider_showtime_ref = pvr_st_id
                existing_st.format = "COUPLE RECLINER"
                existing_st.status = "ACTIVE"

        if new_showtimes:
            session.add_all(new_showtimes)
        await session.commit()
        print(f"Successfully added {len(new_showtimes)} new couple showtimes in Core Monolith Postgres DB!")

if __name__ == "__main__":
    asyncio.run(main())
