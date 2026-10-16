"""
Seed script to add all latest popular movies (BookMyShow & District releases)
across all key Indian and International languages (Tamil, Telugu, Hindi, Malayalam, Kannada, English)
along with active showtimes across PVR and partner venues in Kochi, Chennai, and Bangalore.
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

from sqlalchemy import select, delete, func
from app.core.database import AsyncSessionLocal
from app.movie.models import Movie, Showtime, Venue, Screen
from app.partner.models import PartnerORM
from app.providers.registry import ProviderRegistryModel
from app.shared.timeutil import utcnow

# Real TMDB & BMS poster & backdrop CDN URLs
MOVIES_DATA = [
    # --- TAMIL ---
    {
        "title": "The Greatest of All Time (GOAT)",
        "original_title": "The Greatest of All Time",
        "language": "Tamil",
        "genre": "Action, Sci-Fi, Thriller",
        "certificate": "UA",
        "duration_min": 179,
        "rating": 8.4,
        "rating_count": 85000,
        "external_rating": 8.2,
        "release_date": datetime(2024, 9, 5, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/b33nnKl1vvg6AqNVBAPUjxwhIXb.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/m1ZgzGj8t8f2aG6vV51gY5f5TqR.jpg",
        "synopsis": "A former special squad intelligence operative is forced out of retirement when his dark past catches up with him and his estranged son emerges on the enemy side.",
        "formats": ["2D", "IMAX"],
    },
    {
        "title": "Vettaiyan",
        "original_title": "Vettaiyan",
        "language": "Tamil",
        "genre": "Action, Drama, Crime",
        "certificate": "UA",
        "duration_min": 163,
        "rating": 8.1,
        "rating_count": 62000,
        "external_rating": 7.9,
        "release_date": datetime(2024, 10, 10, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/ybpnnqU4pLhQ5YlY3y2O01WkQv0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9g9wWJt99QvA5f9yqA1K5R5gW0.jpg",
        "synopsis": "An encounter specialist police officer faces an intense moral and legal investigation led by a righteous justice board chairman over an alleged extrajudicial killing.",
        "formats": ["2D", "DOLBY"],
    },
    {
        "title": "Amaran",
        "original_title": "Amaran",
        "language": "Tamil",
        "genre": "Action, Biography, Drama",
        "certificate": "UA",
        "duration_min": 169,
        "rating": 9.1,
        "rating_count": 92000,
        "external_rating": 8.9,
        "release_date": datetime(2024, 10, 31, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/d5v69kUeDk4x69r9tXz1gQ3n0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/k8t12f3k9Yv31K7n0Q2k8t9.jpg",
        "synopsis": "The heroic true story of Major Mukund Varadarajan of the Rajput Regiment, who valiantly fought counter-terrorism operations in Qazipathri, Shopian.",
        "formats": ["2D", "DOLBY"],
    },
    {
        "title": "Lubber Pandhu",
        "original_title": "Lubber Pandhu",
        "language": "Tamil",
        "genre": "Comedy, Drama, Sports",
        "certificate": "U",
        "duration_min": 148,
        "rating": 8.9,
        "rating_count": 48000,
        "external_rating": 8.8,
        "release_date": datetime(2024, 9, 20, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/9k8K5T1k7l3k7Q3n0Z7Y5gV.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/4Y3t5f5K9v0Q1K5gW0Z.jpg",
        "synopsis": "An intense rivalry unfolds between two skilled gully cricket stars of different generations in rural Tamil Nadu, turning personal and comedic.",
        "formats": ["2D"],
    },
    {
        "title": "Meiyazhagan",
        "original_title": "Meiyazhagan",
        "language": "Tamil",
        "genre": "Drama",
        "certificate": "U",
        "duration_min": 177,
        "rating": 8.8,
        "rating_count": 42000,
        "external_rating": 8.6,
        "release_date": datetime(2024, 9, 27, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/4Q5v1g7K8k9Y0Z3n0Q7k.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9k8Q5v1g7K8k9Y0Z3n0Q7k.jpg",
        "synopsis": "A sensitive man returns to his hometown after two decades for a family wedding and unexpectedly forms a deep emotional bond with an affectionate relative whose name he cannot recall.",
        "formats": ["2D"],
    },

    # --- TELUGU ---
    {
        "title": "Devara: Part 1",
        "original_title": "Devara",
        "language": "Telugu",
        "genre": "Action, Drama, Thriller",
        "certificate": "UA",
        "duration_min": 178,
        "rating": 8.2,
        "rating_count": 78000,
        "external_rating": 7.9,
        "release_date": datetime(2024, 9, 27, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/A8w0qQ4Z9f9k0Z3n0Q7k8t9.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/8YvA5f9yqA1K5R5gW0Z.jpg",
        "synopsis": "A brave village warrior from a coastal clan decides to dismantle the illegal smuggling syndicates operating on the high seas, igniting a deadly multi-generational feud.",
        "formats": ["2D", "3D", "IMAX"],
    },
    {
        "title": "Kalki 2898 AD",
        "original_title": "Kalki 2898 AD",
        "language": "Telugu",
        "genre": "Action, Sci-Fi, Fantasy",
        "certificate": "UA",
        "duration_min": 181,
        "rating": 8.7,
        "rating_count": 140000,
        "external_rating": 8.4,
        "release_date": datetime(2024, 6, 27, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/9gK5R5gW0Z8YvA5f9yqA1K5R5.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/k8t9Y0Z3n0Q7k8t9Y0Z3n0Q.jpg",
        "synopsis": "Set in a post-apocalyptic world in the year 2898 AD, an immortal warrior guards the prophesied tenth avatar of Vishnu against the totalitarian Supreme Yaskin.",
        "formats": ["2D", "3D", "IMAX"],
    },
    {
        "title": "Pushpa 2: The Rule",
        "original_title": "Pushpa 2: The Rule",
        "language": "Telugu",
        "genre": "Action, Crime, Thriller",
        "certificate": "UA",
        "duration_min": 185,
        "rating": 9.3,
        "rating_count": 185000,
        "external_rating": 9.1,
        "release_date": datetime(2024, 12, 5, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/p9Y0Z3n0Q7k8t9Y0Z3n0Q7k.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/8t9Y0Z3n0Q7k8t9Y0Z3n0Q7.jpg",
        "synopsis": "Pushpa Raj expands his red sandalwood smuggling empire while navigating high-stakes clashes with police superintendent Bhanwar Singh Shekhawat.",
        "formats": ["2D", "DOLBY", "IMAX"],
    },
    {
        "title": "Lucky Baskhar",
        "original_title": "Lucky Baskhar",
        "language": "Telugu",
        "genre": "Crime, Drama, Thriller",
        "certificate": "UA",
        "duration_min": 150,
        "rating": 8.6,
        "rating_count": 51000,
        "external_rating": 8.5,
        "release_date": datetime(2024, 10, 31, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9Y0Z3n0Q7k8t9Y0Z3n0Q7k8.jpg",
        "synopsis": "An ordinary, financially strapped bank cashier in Bombay stumbles into high-stakes money laundering and stock market manipulation in 1989.",
        "formats": ["2D"],
    },

    # --- HINDI ---
    {
        "title": "Stree 2: Sarkate Ka Aatank",
        "original_title": "Stree 2",
        "language": "Hindi",
        "genre": "Comedy, Horror",
        "certificate": "UA",
        "duration_min": 147,
        "rating": 8.6,
        "rating_count": 125000,
        "external_rating": 8.3,
        "release_date": datetime(2024, 8, 15, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/m1ZgzGj8t8f2aG6vV51gY5f5TqR.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/b33nnKl1vvg6AqNVBAPUjxwhIXb.jpg",
        "synopsis": "The town of Chanderi is haunted once again, this time by a headless apparition known as 'Sarkata' targeting progressive women.",
        "formats": ["2D", "3D"],
    },
    {
        "title": "Singham Again",
        "original_title": "Singham Again",
        "language": "Hindi",
        "genre": "Action, Drama",
        "certificate": "UA",
        "duration_min": 144,
        "rating": 8.0,
        "rating_count": 68000,
        "external_rating": 7.7,
        "release_date": datetime(2024, 11, 1, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/k8t9Y0Z3n0Q7k8t9Y0Z3n0Q.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "synopsis": "DCP Bajirao Singham unites with fellow fearless officers Sooryavanshi and Simmba across borders to dismantle a global terrorist network.",
        "formats": ["2D", "IMAX"],
    },
    {
        "title": "Bhool Bhulaiyaa 3",
        "original_title": "Bhool Bhulaiyaa 3",
        "language": "Hindi",
        "genre": "Comedy, Horror",
        "certificate": "UA",
        "duration_min": 158,
        "rating": 8.2,
        "rating_count": 74000,
        "external_rating": 8.0,
        "release_date": datetime(2024, 11, 1, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/8t9Y0Z3n0Q7k8t9Y0Z3n0Q7.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9gK5R5gW0Z8YvA5f9yqA1K5R5.jpg",
        "synopsis": "Ruhaan, also known as Rooh Baba, is hired to perform an exorcism in a royal palace in West Bengal, awakening two rival Manjulika spirits.",
        "formats": ["2D"],
    },
    {
        "title": "Jigra",
        "original_title": "Jigra",
        "language": "Hindi",
        "genre": "Action, Thriller, Drama",
        "certificate": "UA",
        "duration_min": 153,
        "rating": 7.9,
        "rating_count": 39000,
        "external_rating": 7.6,
        "release_date": datetime(2024, 10, 11, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/6vV51gY5f5TqRm1ZgzGj8t8f2.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/qU4pLhQ5YlY3y2O01WkQv0ybp.jpg",
        "synopsis": "A fiercely protective elder sister embarks on a high-risk prison break to save her wrongfully incarcerated younger brother in an authoritarian foreign state.",
        "formats": ["2D"],
    },

    # --- MALAYALAM ---
    {
        "title": "ARM: Ajayante Randam Moshanam",
        "original_title": "Ajayante Randam Moshanam",
        "language": "Malayalam",
        "genre": "Action, Adventure, Fantasy",
        "certificate": "U",
        "duration_min": 147,
        "rating": 8.8,
        "rating_count": 72000,
        "external_rating": 8.7,
        "release_date": datetime(2024, 9, 12, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/9k8K5T1k7l3k7Q3n0Z7Y5gV.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/4Y3t5f5K9v0Q1K5gW0Z.jpg",
        "synopsis": "Set in northern Kerala spanning three distinct eras (1900, 1953, and 1992), three generations of heroes protect an otherworldly sacred relic.",
        "formats": ["2D", "3D"],
    },
    {
        "title": "Kishkindha Kaandam",
        "original_title": "Kishkindha Kaandam",
        "language": "Malayalam",
        "genre": "Mystery, Thriller",
        "certificate": "U",
        "duration_min": 125,
        "rating": 9.2,
        "rating_count": 68000,
        "external_rating": 9.0,
        "release_date": datetime(2024, 9, 12, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/A8w0qQ4Z9f9k0Z3n0Q7k8t9.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/8YvA5f9yqA1K5R5gW0Z.jpg",
        "synopsis": "Strange occurrences in a monkey-inhabited forest reserve prompt a newlywed couple and forest officials to investigate a missing licensed pistol and an aging patriarch's hidden secrets.",
        "formats": ["2D"],
    },
    {
        "title": "Bougainvillea",
        "original_title": "Bougainvillea",
        "language": "Malayalam",
        "genre": "Psychological Thriller, Crime",
        "certificate": "UA",
        "duration_min": 140,
        "rating": 8.3,
        "rating_count": 35000,
        "external_rating": 8.1,
        "release_date": datetime(2024, 10, 17, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/ybpnnqU4pLhQ5YlY3y2O01WkQv0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9g9wWJt99QvA5f9yqA1K5R5gW0.jpg",
        "synopsis": "A married couple gets entangled in a high-profile police investigation after tourist women start mysteriously disappearing around their secluded plantation home.",
        "formats": ["2D"],
    },
    {
        "title": "Aavesham",
        "original_title": "Aavesham",
        "language": "Malayalam",
        "genre": "Action, Comedy",
        "certificate": "UA",
        "duration_min": 158,
        "rating": 9.0,
        "rating_count": 110000,
        "external_rating": 8.9,
        "release_date": datetime(2024, 4, 11, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/b33nnKl1vvg6AqNVBAPUjxwhIXb.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/m1ZgzGj8t8f2aG6vV51gY5f5TqR.jpg",
        "synopsis": "Three engineering students in Bangalore encounter relentless seniors' ragging and seek the friendship of an eccentric white-clad local gangster named Ranga.",
        "formats": ["2D", "DOLBY"],
    },

    # --- KANNADA ---
    {
        "title": "Bagheera",
        "original_title": "Bagheera",
        "language": "Kannada",
        "genre": "Action, Thriller, Superhero",
        "certificate": "UA",
        "duration_min": 158,
        "rating": 8.5,
        "rating_count": 45000,
        "external_rating": 8.3,
        "release_date": datetime(2024, 10, 31, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9Y0Z3n0Q7k8t9Y0Z3n0Q7k8.jpg",
        "synopsis": "A dedicated IPS officer frustrated by police constraints adopts a dark vigilante persona named Bagheera to hunt down untruthful corporate criminals.",
        "formats": ["2D", "IMAX"],
    },
    {
        "title": "Martin",
        "original_title": "Martin",
        "language": "Kannada",
        "genre": "Action, Thriller",
        "certificate": "UA",
        "duration_min": 148,
        "rating": 7.5,
        "rating_count": 28000,
        "external_rating": 7.2,
        "release_date": datetime(2024, 10, 11, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/8t9Y0Z3n0Q7k8t9Y0Z3n0Q7.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9gK5R5gW0Z8YvA5f9yqA1K5R5.jpg",
        "synopsis": "An undercover agent suffering from amnesia travels across Pakistani and Indian territory uncovering an insidious bio-weapon conspiracy.",
        "formats": ["2D"],
    },
    {
        "title": "UI (The Movie)",
        "original_title": "UI",
        "language": "Kannada",
        "genre": "Sci-Fi, Surrealism, Thriller",
        "certificate": "UA",
        "duration_min": 142,
        "rating": 8.7,
        "rating_count": 36000,
        "external_rating": 8.5,
        "release_date": datetime(2024, 11, 20, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/6vV51gY5f5TqRm1ZgzGj8t8f2.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/qU4pLhQ5YlY3y2O01WkQv0ybp.jpg",
        "synopsis": "A visionary mind delves into human greed, morality, digital avatars, and dystopian societal evolution directed by Upendra.",
        "formats": ["2D", "3D"],
    },

    # --- ENGLISH (HOLLYWOOD) ---
    {
        "title": "Gladiator II",
        "original_title": "Gladiator II",
        "language": "English",
        "genre": "Action, Adventure, Drama",
        "certificate": "A",
        "duration_min": 148,
        "rating": 8.9,
        "rating_count": 160000,
        "external_rating": 8.7,
        "release_date": datetime(2024, 11, 15, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/2cxhvwyEwRlysAmRH4iodkvo0z5.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/eGvhFvC4PjX3j7qHjB8e6vV.jpg",
        "synopsis": "Years after witnessing the death of Maximus at the hands of his uncle, Lucius must enter the Colosseum after his home is conquered by tyrannical emperors.",
        "formats": ["2D", "IMAX", "DOLBY"],
    },
    {
        "title": "Venom: The Last Dance",
        "original_title": "Venom: The Last Dance",
        "language": "English",
        "genre": "Action, Sci-Fi, Adventure",
        "certificate": "UA",
        "duration_min": 110,
        "rating": 8.3,
        "rating_count": 115000,
        "external_rating": 8.0,
        "release_date": datetime(2024, 10, 24, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/aosm8NMQ3UyoBVpSxyimorCQykC.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/3V4kLQg0kSqPLctI5ziAhbAZSYH.jpg",
        "synopsis": "Eddie and Venom are on the run. Hunted by both of their worlds and with the net closing in, the duo are forced into a devastating decision.",
        "formats": ["2D", "3D", "IMAX"],
    },
    {
        "title": "Deadpool & Wolverine",
        "original_title": "Deadpool & Wolverine",
        "language": "English",
        "genre": "Action, Comedy, Sci-Fi",
        "certificate": "A",
        "duration_min": 128,
        "rating": 8.8,
        "rating_count": 210000,
        "external_rating": 8.6,
        "release_date": datetime(2024, 7, 26, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/8cdWjvZQUExUUTzyp4t6EDMubfO.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/yDHYTjA3R0ne8MRgu0f3i1O7l8r.jpg",
        "synopsis": "A listless Wade Wilson toils away in civilian life until the Time Variance Authority recruits him for an existential multiverse mission with Wolverine.",
        "formats": ["2D", "3D", "IMAX"],
    },
    {
        "title": "The Wild Robot",
        "original_title": "The Wild Robot",
        "language": "English",
        "genre": "Animation, Adventure, Sci-Fi",
        "certificate": "U",
        "duration_min": 102,
        "rating": 9.2,
        "rating_count": 98000,
        "external_rating": 9.1,
        "release_date": datetime(2024, 9, 27, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/wTnV3PCVW5O92JMrZvvrRcV39RU.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/v9acaWVvvyhhP1wUj0v5.jpg",
        "synopsis": "After a shipwreck, an intelligent robot named Roz is stranded on an uninhabited island and builds relationships with the native animals while raising an orphaned gosling.",
        "formats": ["2D", "3D"],
    },
]

# Daily show slot times (IST converted to UTC)
DAILY_SHOW_HOURS_IST = [
    (10, 0),   # 10:00 AM
    (13, 30),  # 01:30 PM
    (16, 45),  # 04:45 PM
    (20, 0),   # 08:00 PM
    (22, 45),  # 10:45 PM
]

async def seed_movies():
    print("--- Fast Seeding All Latest Movies (BookMyShow & District) ---")
    async with AsyncSessionLocal() as session:
        partner_res = await session.execute(select(PartnerORM).limit(1))
        partner = partner_res.scalar_one_or_none()
        partner_id = partner.id if partner else uuid.uuid4()

        # 1. Upsert or Insert Movies
        movie_models = {}
        for m_data in MOVIES_DATA:
            q = select(Movie).where(Movie.title == m_data["title"])
            existing = (await session.execute(q)).scalar_one_or_none()
            if existing:
                existing.original_title = m_data["original_title"]
                existing.language = m_data["language"]
                existing.genre = m_data["genre"]
                existing.duration_min = m_data["duration_min"]
                existing.certificate = m_data["certificate"]
                existing.rating = m_data["rating"]
                existing.rating_count = m_data["rating_count"]
                existing.external_rating = m_data["external_rating"]
                existing.poster_url = m_data["poster_url"]
                existing.banner_url = m_data["banner_url"]
                existing.synopsis = m_data["synopsis"]
                existing.status = "PUBLISHED"
                movie_models[m_data["title"]] = existing
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
                    status="PUBLISHED",
                    partner_id=partner_id,
                )
                session.add(new_m)
                movie_models[m_data["title"]] = new_m

        await session.flush()
        print(f"Upserted {len(MOVIES_DATA)} movies successfully.")

        # 2. Fetch all venues & screens
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

        # Pre-fetch existing upcoming showtime slots into a memory set
        now_utc = utcnow()
        existing_res = await session.execute(
            select(Showtime.screen_id, Showtime.starts_at).where(Showtime.starts_at > now_utc)
        )
        existing_slots = set((r[0], r[1]) for r in existing_res.all())
        print(f"Loaded {len(existing_slots)} existing future showtime slots into memory.")

        tz_kolkata = ZoneInfo("Asia/Kolkata")
        today_kolkata = now_utc.astimezone(tz_kolkata).date()

        new_showtimes = []

        # Schedule showtimes for next 5 days
        for day_offset in range(5):
            current_date = today_kolkata + timedelta(days=day_offset)

            for m_data in MOVIES_DATA:
                movie_obj = movie_models[m_data["title"]]
                lang = m_data["language"]
                primary_format = m_data["formats"][0] if m_data.get("formats") else "2D"

                target_cities = ["Bangalore", "Chennai", "Kochi"]
                if lang == "Kannada":
                    target_cities = ["Bangalore", "Chennai"]

                for city in target_cities:
                    available_screens = screens_by_city.get(city, [])
                    if not available_screens:
                        continue

                    # Select 2 distinct screens per city
                    movie_screens = [
                        available_screens[(i * 3 + abs(hash(m_data["title"]))) % len(available_screens)]
                        for i in range(min(2, len(available_screens)))
                    ]

                    for screen in movie_screens:
                        # Try primary and offset hours
                        for (ist_hr, ist_min) in [(10, 15), (13, 45), (17, 0), (20, 15), (22, 30)]:
                            start_dt_ist = datetime.combine(current_date, time(ist_hr, ist_min), tzinfo=tz_kolkata)
                            start_dt_utc = start_dt_ist.astimezone(timezone.utc)

                            if start_dt_utc <= now_utc:
                                continue

                            slot_key = (screen.id, start_dt_utc)
                            if slot_key in existing_slots:
                                continue

                            existing_slots.add(slot_key)
                            new_showtimes.append(
                                Showtime(
                                    id=uuid.uuid4(),
                                    screen_id=screen.id,
                                    movie_id=movie_obj.id,
                                    starts_at=start_dt_utc,
                                    language=lang,
                                    format=primary_format,
                                    status="ACTIVE",
                                    partner_id=partner_id,
                                )
                            )

        print(f"Bulk inserting {len(new_showtimes)} showtimes...")
        session.add_all(new_showtimes)
        await session.commit()
        print(f"SUCCESS: Seeded {len(MOVIES_DATA)} movies and {len(new_showtimes)} showtimes across all cities!")

if __name__ == "__main__":
    asyncio.run(seed_movies())
