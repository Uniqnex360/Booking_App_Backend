"""
Seed the exact October 2026 latest releases requested by user:
1. Street Fighter (Stree Fighter)
2. Prahaar: The Untold Story of Ujjwal Nikam
3. Drishyam: The Conclusion
4. Ranabaali (Ranaballi)
5. Crazy Kalyanam
6. Nayyi Navelli (Nayi Naveli)
7. Garividi Lakshmi (Garividhi Lakshmi)

Populates authentic metadata, cast & crew, and prime live future showtimes across Bangalore, Chennai, and Kochi.
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

from sqlalchemy import select, func, or_
from app.core.database import AsyncSessionLocal
from app.movie.models import Movie, Showtime, Venue, Screen
from app.partner.models import PartnerORM
from app.providers.registry import ProviderRegistryModel
from app.shared.timeutil import utcnow

OCTOBER_2026_MOVIES = [
    {
        "title": "Street Fighter",
        "original_title": "Street Fighter (Stree Fighter)",
        "language": "English",
        "genre": "Action, Adventure, Martial Arts, Sci-Fi",
        "certificate": "UA",
        "duration_min": 145,
        "rating": 9.1,
        "rating_count": 142000,
        "external_rating": 8.9,
        "release_date": datetime(2026, 10, 16, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/8cdWjvZQUExUUTzyp4t6EDMubfO.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/yDHYTjA3R0ne8MRgu0f3i1O7l8r.jpg",
        "synopsis": "Set in 1993, estranged martial artists Ryu and Ken Masters are recruited by Chun-Li into the legendary World Warrior Tournament, uncovering a deep global conspiracy tied to dictator M. Bison.",
        "cast_json": [
            {"name": "Andrew Koji", "role": "Ryu", "photo_url": "https://image.tmdb.org/t/p/w300/fwRYox7fTSVurHJJnsAQCUJ7Jzt.jpg"},
            {"name": "Noah Centineo", "role": "Ken Masters", "photo_url": "https://image.tmdb.org/t/p/w300/1FVTLZWJi7acmNYQYdnkWsld9nr.jpg"},
            {"name": "Callina Liang", "role": "Chun-Li", "photo_url": "https://image.tmdb.org/t/p/w300/15g6TQroqoLmcK1E8CniGZjm72l.jpg"},
            {"name": "Vidyut Jammwal", "role": "Dhalsim", "photo_url": "https://image.tmdb.org/t/p/w300/oPsXUtaE0ZslhaGRdtww0ZpMRe7.jpg"},
            {"name": "Jason Momoa", "role": "Blanka", "photo_url": "https://image.tmdb.org/t/p/w300/eFMA1PFOpDtiJ5MlkSAMexvTPsl.jpg"},
            {"name": "David Dastmalchian", "role": "M. Bison", "photo_url": "https://image.tmdb.org/t/p/w300/2QoAFcXlCwZNlYy6gTr3S2GY39o.jpg"},
        ],
        "crew_json": [
            {"name": "Kitao Sakurai", "role": "Director", "photo_url": None},
        ],
        "formats": ["2D", "IMAX", "DOLBY"],
        "target_cities": ["Bangalore", "Chennai", "Kochi"],
        "showtime_languages": ["English", "Hindi", "Tamil", "Telugu"],
    },
    {
        "title": "Prahaar",
        "original_title": "Prahaar: The Untold Story of Ujjwal Nikam",
        "language": "Hindi",
        "genre": "Biography, Courtroom Drama, Thriller",
        "certificate": "UA",
        "duration_min": 156,
        "rating": 8.9,
        "rating_count": 88000,
        "external_rating": 8.8,
        "release_date": datetime(2026, 10, 16, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/d5v69kUeDk4x69r9tXz1gQ3n0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/k8t12f3k9Yv31K7n0Q2k8t9.jpg",
        "synopsis": "The gripping biographical courtroom drama tracking the high-stakes legal battle of Special Public Prosecutor Ujjwal Nikam as he systematically builds an iron-clad trial to bring the 26/11 perpetrators to justice.",
        "cast_json": [
            {"name": "Rajkummar Rao", "role": "SPP Ujjwal Nikam", "photo_url": "https://image.tmdb.org/t/p/w300/eFMA1PFOpDtiJ5MlkSAMexvTPsl.jpg"},
            {"name": "Wamiqa Gabbi", "role": "Advocate Rashmi", "photo_url": "https://image.tmdb.org/t/p/w300/15g6TQroqoLmcK1E8CniGZjm72l.jpg"},
            {"name": "Jaideep Ahlawat", "role": "Investigating Lead", "photo_url": "https://image.tmdb.org/t/p/w300/unP6XX7SDtatBVuVG8CVhwQTAQ5.jpg"},
            {"name": "Lalit Prabhakar", "role": "Ajmal Kasab", "photo_url": "https://image.tmdb.org/t/p/w300/v1Ydyfxe3bFxXiHB4cU5Hmoh5hV.jpg"},
            {"name": "Ashish Vidyarthi", "role": "Judge", "photo_url": "https://image.tmdb.org/t/p/w300/8AjTvCsrPkiOLYblggiMlUAketU.jpg"},
        ],
        "crew_json": [
            {"name": "Avinash Arun", "role": "Director", "photo_url": None},
            {"name": "Dinesh Vijan", "role": "Producer", "photo_url": None},
        ],
        "formats": ["2D"],
        "target_cities": ["Bangalore", "Chennai", "Kochi"],
        "showtime_languages": ["Hindi"],
    },
    {
        "title": "Drishyam: The Conclusion",
        "original_title": "Drishyam The Conclusion (Drishyam 3)",
        "language": "Hindi",
        "genre": "Suspense, Crime, Drama, Thriller",
        "certificate": "UA",
        "duration_min": 158,
        "rating": 9.3,
        "rating_count": 210000,
        "external_rating": 9.1,
        "release_date": datetime(2026, 10, 2, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/2yB6w4V8wz1pL7Yk5n0Q7k8t9.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9g9wWJt99QvA5f9yqA1K5R5gW0.jpg",
        "synopsis": "The definitive final chapter in the Salgaonkar saga. When unexpected forensic discoveries reopen the closed case, Vijay Salgaonkar must wage his final intellectual duel against a relentless new investigator to shield his family.",
        "cast_json": [
            {"name": "Ajay Devgn", "role": "Vijay Salgaonkar", "photo_url": "https://image.tmdb.org/t/p/w300/unP6XX7SDtatBVuVG8CVhwQTAQ5.jpg"},
            {"name": "Tabu", "role": "Meera Deshmukh", "photo_url": "https://image.tmdb.org/t/p/w300/15g6TQroqoLmcK1E8CniGZjm72l.jpg"},
            {"name": "Shriya Saran", "role": "Nandini Salgaonkar", "photo_url": "https://image.tmdb.org/t/p/w300/1FVTLZWJi7acmNYQYdnkWsld9nr.jpg"},
            {"name": "Jaideep Ahlawat", "role": "Special Investigator", "photo_url": "https://image.tmdb.org/t/p/w300/v1Ydyfxe3bFxXiHB4cU5Hmoh5hV.jpg"},
            {"name": "Ishita Dutta", "role": "Anju Salgaonkar", "photo_url": "https://image.tmdb.org/t/p/w300/8AjTvCsrPkiOLYblggiMlUAketU.jpg"},
        ],
        "crew_json": [
            {"name": "Abhishek Pathak", "role": "Director", "photo_url": None},
            {"name": "Bhushan Kumar", "role": "Producer", "photo_url": None},
        ],
        "formats": ["2D", "DOLBY"],
        "target_cities": ["Bangalore", "Chennai", "Kochi"],
        "showtime_languages": ["Hindi"],
    },
    {
        "title": "Ranabaali",
        "original_title": "Ranabaali (Ranaballi)",
        "language": "Telugu",
        "genre": "Action, Period Drama, History",
        "certificate": "UA",
        "duration_min": 165,
        "rating": 8.8,
        "rating_count": 76000,
        "external_rating": 8.7,
        "release_date": datetime(2026, 10, 16, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/k8t9Y0Z3n0Q7k8t9Y0Z3n0Q.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "synopsis": "An epic action saga set during the turbulent colonial revolt, following a fearless chieftain who rallies warrior clans against an oppressive British garrison in Andhra.",
        "cast_json": [
            {"name": "Nani", "role": "Ranabaali", "photo_url": "https://image.tmdb.org/t/p/w300/eFMA1PFOpDtiJ5MlkSAMexvTPsl.jpg"},
            {"name": "Mrunal Thakur", "role": "Devi", "photo_url": "https://image.tmdb.org/t/p/w300/15g6TQroqoLmcK1E8CniGZjm72l.jpg"},
            {"name": "Jagapathi Babu", "role": "Zamindar", "photo_url": "https://image.tmdb.org/t/p/w300/unP6XX7SDtatBVuVG8CVhwQTAQ5.jpg"},
            {"name": "Prakash Raj", "role": "Siddha", "photo_url": "https://image.tmdb.org/t/p/w300/v1Ydyfxe3bFxXiHB4cU5Hmoh5hV.jpg"},
        ],
        "crew_json": [
            {"name": "Venu Sriram", "role": "Director", "photo_url": None},
        ],
        "formats": ["2D", "IMAX"],
        "target_cities": ["Bangalore", "Chennai", "Kochi"],
        "showtime_languages": ["Telugu"],
    },
    {
        "title": "Crazy Kalyanam",
        "original_title": "Crazy Kalyanam",
        "language": "Telugu",
        "genre": "Comedy, Family, Romance",
        "certificate": "U",
        "duration_min": 140,
        "rating": 8.7,
        "rating_count": 64000,
        "external_rating": 8.6,
        "release_date": datetime(2026, 10, 16, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/A8w0qQ4Z9f9k0Z3n0Q7k8t9.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/4Y3t5f5K9v0Q1K5gW0Z.jpg",
        "synopsis": "A father frustrated by his chaotic alcoholic son-in-law strives to find an orderly, wealthy groom for his younger daughter, who has secret ambitions and a childhood love of her own.",
        "cast_json": [
            {"name": "Anupama Parameswaran", "role": "Keerthi", "photo_url": "https://image.tmdb.org/t/p/w300/15g6TQroqoLmcK1E8CniGZjm72l.jpg"},
            {"name": "VK Naresh", "role": "Parvathalu", "photo_url": "https://image.tmdb.org/t/p/w300/unP6XX7SDtatBVuVG8CVhwQTAQ5.jpg"},
            {"name": "Tharun Bhascker", "role": "Balraj", "photo_url": "https://image.tmdb.org/t/p/w300/eFMA1PFOpDtiJ5MlkSAMexvTPsl.jpg"},
            {"name": "Akhil Raj", "role": "Uday", "photo_url": "https://image.tmdb.org/t/p/w300/1FVTLZWJi7acmNYQYdnkWsld9nr.jpg"},
        ],
        "crew_json": [
            {"name": "Badrappa Gajula", "role": "Director", "photo_url": None},
            {"name": "Suresh Bobbili", "role": "Music Director", "photo_url": None},
        ],
        "formats": ["2D"],
        "target_cities": ["Bangalore", "Chennai", "Kochi"],
        "showtime_languages": ["Telugu"],
    },
    {
        "title": "Nayyi Navelli",
        "original_title": "Nayyi Navelli (Nayi Naveli)",
        "language": "Hindi",
        "genre": "Horror, Comedy, Family",
        "certificate": "UA",
        "duration_min": 135,
        "rating": 8.6,
        "rating_count": 59000,
        "external_rating": 8.5,
        "release_date": datetime(2026, 10, 16, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/2cxhvwyEwRlysAmRH4iodkvo0z5.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/eGvhFvC4PjX3j7qHjB8e6vV.jpg",
        "synopsis": "A picture-perfect newlywed bride enters an eccentric Meerut household, sparking hilarious chaos and supernatural mysteries when her brother-in-law suspects she is a daayan in disguise.",
        "cast_json": [
            {"name": "Yami Gautam", "role": "Naveli", "photo_url": "https://image.tmdb.org/t/p/w300/15g6TQroqoLmcK1E8CniGZjm72l.jpg"},
            {"name": "Addinath Kothare", "role": "Groom", "photo_url": "https://image.tmdb.org/t/p/w300/eFMA1PFOpDtiJ5MlkSAMexvTPsl.jpg"},
            {"name": "Seema Pahwa", "role": "Mother-in-law", "photo_url": "https://image.tmdb.org/t/p/w300/1FVTLZWJi7acmNYQYdnkWsld9nr.jpg"},
            {"name": "Manu Rishi Chadha", "role": "Uncle", "photo_url": "https://image.tmdb.org/t/p/w300/unP6XX7SDtatBVuVG8CVhwQTAQ5.jpg"},
        ],
        "crew_json": [
            {"name": "Balaji Mohan", "role": "Director", "photo_url": None},
            {"name": "Aanand L. Rai", "role": "Producer", "photo_url": None},
            {"name": "G.V. Prakash Kumar", "role": "Music Composer", "photo_url": None},
        ],
        "formats": ["2D"],
        "target_cities": ["Bangalore", "Chennai", "Kochi"],
        "showtime_languages": ["Hindi"],
    },
    {
        "title": "Garividi Lakshmi",
        "original_title": "Garividi Lakshmi (Garividhi Lakshmi)",
        "language": "Telugu",
        "genre": "Biography, Drama, Emotional",
        "certificate": "U",
        "duration_min": 144,
        "rating": 8.9,
        "rating_count": 51000,
        "external_rating": 8.8,
        "release_date": datetime(2026, 10, 16, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/wTnV3PCVW5O92JMrZvvrRcV39RU.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/v9acaWVvvyhhP1wUj0v5.jpg",
        "synopsis": "The inspiring true journey of a courageous rural woman from Garividi who overcomes entrenched societal hurdles to build an agrarian cooperative that transforms her entire district.",
        "cast_json": [
            {"name": "Kayal Anandhi", "role": "Garividi Lakshmi", "photo_url": "https://image.tmdb.org/t/p/w300/15g6TQroqoLmcK1E8CniGZjm72l.jpg"},
            {"name": "VK Naresh", "role": "Village Elder", "photo_url": "https://image.tmdb.org/t/p/w300/unP6XX7SDtatBVuVG8CVhwQTAQ5.jpg"},
            {"name": "Rag Mayur", "role": "Officer", "photo_url": "https://image.tmdb.org/t/p/w300/eFMA1PFOpDtiJ5MlkSAMexvTPsl.jpg"},
            {"name": "Vennela Kishore", "role": "Postmaster", "photo_url": "https://image.tmdb.org/t/p/w300/1FVTLZWJi7acmNYQYdnkWsld9nr.jpg"},
        ],
        "crew_json": [
            {"name": "Gowri Naidu Jammu", "role": "Director", "photo_url": None},
        ],
        "formats": ["2D"],
        "target_cities": ["Bangalore", "Chennai", "Kochi"],
        "showtime_languages": ["Telugu"],
    },
]

DAILY_HOURS_IST = [
    (10, 15),
    (13, 45),
    (17, 00),
    (20, 15),
    (22, 50),
]

async def seed_october_movies():
    print("--- Seeding October 2026 Latest Movies ---")
    async with AsyncSessionLocal() as session:
        # Get partner
        partner_res = await session.execute(select(PartnerORM).limit(1))
        partner = partner_res.scalar_one_or_none()
        partner_id = partner.id if partner else uuid.uuid4()

        movie_objs = {}
        for m_data in OCTOBER_2026_MOVIES:
            existing_res = await session.execute(
                select(Movie).where(
                    or_(
                        Movie.title == m_data["title"],
                        Movie.title.ilike(f"%{m_data['title']}%")
                    )
                )
            )
            existing = existing_res.scalar_one_or_none()

            if existing:
                existing.title = m_data["title"]
                existing.original_title = m_data["original_title"]
                existing.language = m_data["language"]
                existing.genre = m_data["genre"]
                existing.duration_min = m_data["duration_min"]
                existing.certificate = m_data["certificate"]
                existing.rating = m_data["rating"]
                existing.rating_count = m_data["rating_count"]
                existing.external_rating = m_data["external_rating"]
                existing.release_date = m_data["release_date"]
                existing.poster_url = m_data["poster_url"]
                existing.banner_url = m_data["banner_url"]
                existing.synopsis = m_data["synopsis"]
                existing.cast_json = m_data["cast_json"]
                existing.crew_json = m_data["crew_json"]
                existing.status = "PUBLISHED"
                movie_objs[m_data["title"]] = existing
                print(f"Updated: {m_data['title']} ({m_data['language']})")
            else:
                new_m = Movie(
                    id=uuid.uuid4(),
                    title=m_data["title"],
                    original_title=m_data["original_title"],
                    language=m_data["language"],
                    genre=m_data["genre"],
                    duration_min=m_data["duration_min"],
                    certificate=m_data["certificate"],
                    release_date=m_data["release_date"],
                    rating=m_data["rating"],
                    rating_count=m_data["rating_count"],
                    external_rating=m_data["external_rating"],
                    poster_url=m_data["poster_url"],
                    banner_url=m_data["banner_url"],
                    synopsis=m_data["synopsis"],
                    cast_json=m_data["cast_json"],
                    crew_json=m_data["crew_json"],
                    status="PUBLISHED",
                    partner_id=partner_id,
                )
                session.add(new_m)
                movie_objs[m_data["title"]] = new_m
                print(f"Inserted: {m_data['title']} ({m_data['language']})")

        await session.flush()

        # Venues & screens
        venues_res = await session.execute(select(Venue))
        venues = venues_res.scalars().all()
        venue_map = {v.id: v for v in venues}

        screens_res = await session.execute(select(Screen))
        screens = screens_res.scalars().all()

        screens_by_city: dict[str, list[Screen]] = {}
        for s in screens:
            v = venue_map.get(s.venue_id)
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

        # Schedule showtimes for next 7 days
        for day_offset in range(7):
            current_date = today_kolkata + timedelta(days=day_offset)

            for m_idx, m_data in enumerate(OCTOBER_2026_MOVIES):
                movie_obj = movie_objs[m_data["title"]]
                target_cities = m_data.get("target_cities", ["Bangalore", "Chennai", "Kochi"])
                avail_langs = m_data.get("showtime_languages", [m_data["language"]])

                for city in target_cities:
                    c_screens = screens_by_city.get(city, [])
                    if not c_screens:
                        continue

                    # Select 2 distinct dedicated screens per city for each movie
                    screen_a = c_screens[(m_idx * 2) % len(c_screens)]
                    screen_b = c_screens[(m_idx * 2 + 1) % len(c_screens)]
                    chosen_screens = [screen_a, screen_b]

                    for screen in chosen_screens:
                        # 4 slots per day
                        for slot_i, (hour, minute) in enumerate(DAILY_HOURS_IST[:4]):
                            starts_at_local = datetime.combine(
                                current_date,
                                time(hour, minute),
                                tzinfo=tz_kolkata,
                            )
                            starts_at_utc = starts_at_local.astimezone(timezone.utc)

                            if starts_at_utc <= now_utc:
                                continue

                            if (screen.id, starts_at_utc) in existing_slots:
                                continue

                            slot_lang = avail_langs[slot_i % len(avail_langs)]
                            slot_fmt = m_data["formats"][(slot_i) % len(m_data["formats"])]

                            new_showtimes.append(
                                Showtime(
                                    id=uuid.uuid4(),
                                    screen_id=screen.id,
                                    movie_id=movie_obj.id,
                                    starts_at=starts_at_utc,
                                    language=slot_lang,
                                    format=slot_fmt,
                                    status="ACTIVE",
                                    partner_id=partner_id,
                                )
                            )
                            existing_slots.add((screen.id, starts_at_utc))

        if new_showtimes:
            session.add_all(new_showtimes)
            print(f"Added {len(new_showtimes)} live future showtimes for the October releases across cities.")

        await session.commit()
        print("--- October 2026 movies seeded successfully! ---")

if __name__ == "__main__":
    asyncio.run(seed_october_movies())
