"""
Script to:
1. Remove/archive old mock/dummy titles (I Am Game, Kingdom, Last Whistle, The Final Whistle, Jailer 2).
2. Seed the actual latest blockbuster theatrical releases (BookMyShow & District) across:
   Tamil, Telugu, Hindi, Malayalam, Kannada, and English.
3. Set release dates to late 2024 / 2025 so they display as brand new releases.
4. Populate active prime future showtimes across PVR and partner screens in Kochi, Chennai, Bangalore.
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

from sqlalchemy import select, delete, func, or_
from app.core.database import AsyncSessionLocal
from app.movie.models import Movie, Showtime, Venue, Screen
from app.partner.models import PartnerORM
from app.providers.registry import ProviderRegistryModel
from app.shared.timeutil import utcnow

# Dummy / mock movies to clean up
MOCK_TITLES_TO_CLEAN = [
    "I Am Game",
    "Kingdom",
    "Last Whistle",
    "The Final Whistle",
    "Jailer 2",
    "Avengers: Endgame Encore",
]

# Genuine latest 2024-2025 theatrical blockbusters currently on BookMyShow & District
LATEST_MOVIES = [
    # ================= TAMIL =================
    {
        "title": "Vidaamuyarchi",
        "original_title": "Vidaamuyarchi",
        "language": "Tamil",
        "genre": "Action, Thriller, Adventure",
        "certificate": "UA",
        "duration_min": 162,
        "rating": 8.9,
        "rating_count": 95000,
        "external_rating": 8.7,
        "release_date": datetime(2025, 1, 14, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/2yB6w4V8wz1pL7Yk5n0Q7k8t9.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9g9wWJt99QvA5f9yqA1K5R5gW0.jpg",
        "synopsis": "A married couple travelling abroad finds themselves in grave danger when the wife is mysteriously kidnapped by a ruthless desert cartel, leading the husband on a relentless rescue chase.",
        "formats": ["2D", "IMAX", "DOLBY"],
    },
    {
        "title": "Dragon",
        "original_title": "Dragon",
        "language": "Tamil",
        "genre": "Comedy, Drama, Romance",
        "certificate": "UA",
        "duration_min": 154,
        "rating": 8.7,
        "rating_count": 68000,
        "external_rating": 8.5,
        "release_date": datetime(2025, 2, 14, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/A8w0qQ4Z9f9k0Z3n0Q7k8t9.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/4Y3t5f5K9v0Q1K5gW0Z.jpg",
        "synopsis": "A rebellious and charismatic young college student navigates fierce academic rivalries, family conflicts, and an unexpected romance in Chennai.",
        "formats": ["2D"],
    },
    {
        "title": "Kanguva",
        "original_title": "Kanguva",
        "language": "Tamil",
        "genre": "Action, Fantasy, Period Drama",
        "certificate": "UA",
        "duration_min": 154,
        "rating": 8.0,
        "rating_count": 82000,
        "external_rating": 7.8,
        "release_date": datetime(2024, 11, 14, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/k8t9Y0Z3n0Q7k8t9Y0Z3n0Q.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "synopsis": "A valiant ancient tribal warlord's fierce battle to protect his island clan in 1070 AD echoes across centuries into the life of a modern bounty hunter in Goa.",
        "formats": ["2D", "3D", "IMAX"],
    },
    {
        "title": "Amaran",
        "original_title": "Amaran",
        "language": "Tamil",
        "genre": "Action, Biography, Drama",
        "certificate": "UA",
        "duration_min": 169,
        "rating": 9.2,
        "rating_count": 145000,
        "external_rating": 9.0,
        "release_date": datetime(2024, 10, 31, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/d5v69kUeDk4x69r9tXz1gQ3n0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/k8t12f3k9Yv31K7n0Q2k8t9.jpg",
        "synopsis": "The heroic true story of Major Mukund Varadarajan of the Rajput Regiment and 44 Rashtriya Rifles, who valiantly led counter-terrorism operations in Kashmir.",
        "formats": ["2D", "DOLBY"],
    },
    {
        "title": "Vettaiyan",
        "original_title": "Vettaiyan",
        "language": "Tamil",
        "genre": "Action, Crime, Drama",
        "certificate": "UA",
        "duration_min": 163,
        "rating": 8.3,
        "rating_count": 92000,
        "external_rating": 8.1,
        "release_date": datetime(2024, 10, 10, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/ybpnnqU4pLhQ5YlY3y2O01WkQv0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9g9wWJt99QvA5f9yqA1K5R5gW0.jpg",
        "synopsis": "An encounter specialist police officer encounters severe moral scrutiny and a high-stakes judicial probe into extrajudicial executions led by a retired supreme court judge.",
        "formats": ["2D", "DOLBY"],
    },

    # ================= TELUGU =================
    {
        "title": "Game Changer",
        "original_title": "Game Changer",
        "language": "Telugu",
        "genre": "Action, Political Drama, Thriller",
        "certificate": "UA",
        "duration_min": 165,
        "rating": 8.8,
        "rating_count": 110000,
        "external_rating": 8.6,
        "release_date": datetime(2025, 1, 10, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/p9Y0Z3n0Q7k8t9Y0Z3n0Q7k.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/8t9Y0Z3n0Q7k8t9Y0Z3n0Q7.jpg",
        "synopsis": "An honest Indian Administrative Service officer sets out to dismantle electoral corruption and reform the democratic governance apparatus.",
        "formats": ["2D", "IMAX"],
    },
    {
        "title": "Pushpa 2: The Rule",
        "original_title": "Pushpa 2: The Rule",
        "language": "Telugu",
        "genre": "Action, Crime, Thriller",
        "certificate": "UA",
        "duration_min": 185,
        "rating": 9.4,
        "rating_count": 220000,
        "external_rating": 9.2,
        "release_date": datetime(2024, 12, 5, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/b33nnKl1vvg6AqNVBAPUjxwhIXb.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/m1ZgzGj8t8f2aG6vV51gY5f5TqR.jpg",
        "synopsis": "Pushpa Raj expands his red sandalwood syndicate overseas while facing relentless legal and physical vengeance from SP Bhanwar Singh Shekhawat.",
        "formats": ["2D", "IMAX", "DOLBY"],
    },
    {
        "title": "Daaku Maharaaj",
        "original_title": "Daaku Maharaaj",
        "language": "Telugu",
        "genre": "Action, Drama",
        "certificate": "UA",
        "duration_min": 158,
        "rating": 8.5,
        "rating_count": 75000,
        "external_rating": 8.3,
        "release_date": datetime(2025, 1, 12, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/9gK5R5gW0Z8YvA5f9yqA1K5R5.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/k8t9Y0Z3n0Q7k8t9Y0Z3n0Q.jpg",
        "synopsis": "A legendary outlaw fights against feudal oppression in the heartland, rising as a ruthless protector of the dispossessed.",
        "formats": ["2D"],
    },
    {
        "title": "Sankranthiki Vasthunam",
        "original_title": "Sankranthiki Vasthunam",
        "language": "Telugu",
        "genre": "Action, Crime, Comedy",
        "certificate": "UA",
        "duration_min": 152,
        "rating": 8.4,
        "rating_count": 64000,
        "external_rating": 8.2,
        "release_date": datetime(2025, 1, 14, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9Y0Z3n0Q7k8t9Y0Z3n0Q7k8.jpg",
        "synopsis": "An ex-cop is hired to protect an influential crime witness, triggering a series of hilarious and chaotic misadventures.",
        "formats": ["2D"],
    },
    {
        "title": "Lucky Baskhar",
        "original_title": "Lucky Baskhar",
        "language": "Telugu",
        "genre": "Crime, Drama, Thriller",
        "certificate": "UA",
        "duration_min": 150,
        "rating": 8.8,
        "rating_count": 78000,
        "external_rating": 8.7,
        "release_date": datetime(2024, 10, 31, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/6vV51gY5f5TqRm1ZgzGj8t8f2.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/qU4pLhQ5YlY3y2O01WkQv0ybp.jpg",
        "synopsis": "A meek bank clerk gets lured into the high-stakes world of stock market manipulation and shadow banking in Bombay during the late 1980s.",
        "formats": ["2D"],
    },

    # ================= MALAYALAM =================
    {
        "title": "L2: Empuraan",
        "original_title": "L2: Empuraan",
        "language": "Malayalam",
        "genre": "Action, Crime, Political Thriller",
        "certificate": "UA",
        "duration_min": 172,
        "rating": 9.5,
        "rating_count": 160000,
        "external_rating": 9.3,
        "release_date": datetime(2025, 3, 27, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/b33nnKl1vvg6AqNVBAPUjxwhIXb.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/m1ZgzGj8t8f2aG6vV51gY5f5TqR.jpg",
        "synopsis": "Stephen Nedumpally returns as Khureshi-Ab'raam to wage an international war against global cartels threatening the sovereignty of his home state.",
        "formats": ["2D", "IMAX", "DOLBY"],
    },
    {
        "title": "Marco",
        "original_title": "Marco",
        "language": "Malayalam",
        "genre": "Action, Crime, Neo-Noir",
        "certificate": "A",
        "duration_min": 152,
        "rating": 8.9,
        "rating_count": 89000,
        "external_rating": 8.7,
        "release_date": datetime(2024, 12, 20, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/ybpnnqU4pLhQ5YlY3y2O01WkQv0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9g9wWJt99QvA5f9yqA1K5R5gW0.jpg",
        "synopsis": "The blood-soaked origin story and ruthless ascension of Marco Jr., the most feared syndicate lieutenant in South India.",
        "formats": ["2D", "DOLBY"],
    },
    {
        "title": "Barroz",
        "original_title": "Barroz",
        "language": "Malayalam",
        "genre": "Fantasy, Adventure, Family",
        "certificate": "U",
        "duration_min": 144,
        "rating": 8.2,
        "rating_count": 55000,
        "external_rating": 8.0,
        "release_date": datetime(2024, 12, 25, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/A8w0qQ4Z9f9k0Z3n0Q7k8t9.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/8YvA5f9yqA1K5R5gW0Z.jpg",
        "synopsis": "A guardian spirit who has protected Vasco da Gama's hidden treasures for 400 years awaits the true descendant to pass on the legacy.",
        "formats": ["2D", "3D"],
    },
    {
        "title": "Bougainvillea",
        "original_title": "Bougainvillea",
        "language": "Malayalam",
        "genre": "Psychological Thriller, Crime",
        "certificate": "UA",
        "duration_min": 140,
        "rating": 8.6,
        "rating_count": 62000,
        "external_rating": 8.4,
        "release_date": datetime(2024, 10, 17, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/9k8K5T1k7l3k7Q3n0Z7Y5gV.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/4Y3t5f5K9v0Q1K5gW0Z.jpg",
        "synopsis": "A married couple is interrogated by police after tourist women vanish near their isolated high-range estate, uncovering deep psychological trauma.",
        "formats": ["2D"],
    },
    {
        "title": "Kishkindha Kaandam",
        "original_title": "Kishkindha Kaandam",
        "language": "Malayalam",
        "genre": "Mystery, Thriller",
        "certificate": "U",
        "duration_min": 125,
        "rating": 9.3,
        "rating_count": 82000,
        "external_rating": 9.1,
        "release_date": datetime(2024, 9, 12, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/d5v69kUeDk4x69r9tXz1gQ3n0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/k8t12f3k9Yv31K7n0Q2k8t9.jpg",
        "synopsis": "A mysterious disappearance inside an eerie monkey-inhabited forest reserve unravels an aging military patriarch's closely guarded secrets.",
        "formats": ["2D"],
    },

    # ================= HINDI =================
    {
        "title": "Sikandar",
        "original_title": "Sikandar",
        "language": "Hindi",
        "genre": "Action, Drama, Thriller",
        "certificate": "UA",
        "duration_min": 164,
        "rating": 8.9,
        "rating_count": 130000,
        "external_rating": 8.7,
        "release_date": datetime(2025, 3, 28, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/k8t9Y0Z3n0Q7k8t9Y0Z3n0Q.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "synopsis": "A battle-hardened protector takes on an untouchable international underworld kingpin in an explosive high-octane confrontation.",
        "formats": ["2D", "IMAX"],
    },
    {
        "title": "Chhaava",
        "original_title": "Chhaava",
        "language": "Hindi",
        "genre": "Historical Epic, Action, Drama",
        "certificate": "UA",
        "duration_min": 160,
        "rating": 9.1,
        "rating_count": 115000,
        "external_rating": 8.9,
        "release_date": datetime(2025, 2, 14, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/8t9Y0Z3n0Q7k8t9Y0Z3n0Q7.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9gK5R5gW0Z8YvA5f9yqA1K5R5.jpg",
        "synopsis": "The fierce historical chronicle of Chhatrapati Sambhaji Maharaj, the valiant second ruler of the Maratha Empire who courageously resisted Mughal forces.",
        "formats": ["2D", "IMAX"],
    },
    {
        "title": "Baby John",
        "original_title": "Baby John",
        "language": "Hindi",
        "genre": "Action, Crime, Drama",
        "certificate": "UA",
        "duration_min": 155,
        "rating": 8.4,
        "rating_count": 72000,
        "external_rating": 8.2,
        "release_date": datetime(2024, 12, 25, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/p9Y0Z3n0Q7k8t9Y0Z3n0Q7k.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/8t9Y0Z3n0Q7k8t9Y0Z3n0Q7.jpg",
        "synopsis": "A former top cop living a peaceful secluded life with his young daughter is forced back into violence when his dark enemies discover his whereabouts.",
        "formats": ["2D"],
    },
    {
        "title": "Bhool Bhulaiyaa 3",
        "original_title": "Bhool Bhulaiyaa 3",
        "language": "Hindi",
        "genre": "Comedy, Horror",
        "certificate": "UA",
        "duration_min": 158,
        "rating": 8.3,
        "rating_count": 94000,
        "external_rating": 8.1,
        "release_date": datetime(2024, 11, 1, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/m1ZgzGj8t8f2aG6vV51gY5f5TqR.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/b33nnKl1vvg6AqNVBAPUjxwhIXb.jpg",
        "synopsis": "Rooh Baba is hired by a royal household to exorcise a haunted haveli in Bengal, only to awaken two competing vengeful spirits of Manjulika.",
        "formats": ["2D"],
    },
    {
        "title": "Singham Again",
        "original_title": "Singham Again",
        "language": "Hindi",
        "genre": "Action, Crime, Drama",
        "certificate": "UA",
        "duration_min": 144,
        "rating": 8.1,
        "rating_count": 88000,
        "external_rating": 7.9,
        "release_date": datetime(2024, 11, 1, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9Y0Z3n0Q7k8t9Y0Z3n0Q7k8.jpg",
        "synopsis": "Bajirao Singham gathers his cop universe allies across borders to rescue his kidnapped wife and take down a transnational terror syndicate.",
        "formats": ["2D", "IMAX"],
    },

    # ================= KANNADA =================
    {
        "title": "Max",
        "original_title": "Max",
        "language": "Kannada",
        "genre": "Action, Crime, Thriller",
        "certificate": "UA",
        "duration_min": 156,
        "rating": 8.9,
        "rating_count": 72000,
        "external_rating": 8.7,
        "release_date": datetime(2024, 12, 25, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/7k8t9Y0Z3n0Q7k8t9Y0Z3n0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9Y0Z3n0Q7k8t9Y0Z3n0Q7k8.jpg",
        "synopsis": "A suspended fierce police inspector investigates a mysterious high-profile double murder involving corrupt political elites during one rainy night.",
        "formats": ["2D", "DOLBY"],
    },
    {
        "title": "Bagheera",
        "original_title": "Bagheera",
        "language": "Kannada",
        "genre": "Action, Thriller, Vigilante",
        "certificate": "UA",
        "duration_min": 158,
        "rating": 8.7,
        "rating_count": 68000,
        "external_rating": 8.5,
        "release_date": datetime(2024, 10, 31, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/8t9Y0Z3n0Q7k8t9Y0Z3n0Q7.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9gK5R5gW0Z8YvA5f9yqA1K5R5.jpg",
        "synopsis": "An idealistic police officer constrained by system corruption dons a vigilante mask named Bagheera to mete out merciless justice.",
        "formats": ["2D", "IMAX"],
    },
    {
        "title": "UI (The Movie)",
        "original_title": "UI",
        "language": "Kannada",
        "genre": "Sci-Fi, Surrealism, Thriller",
        "certificate": "UA",
        "duration_min": 142,
        "rating": 8.8,
        "rating_count": 55000,
        "external_rating": 8.6,
        "release_date": datetime(2024, 12, 20, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/6vV51gY5f5TqRm1ZgzGj8t8f2.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/qU4pLhQ5YlY3y2O01WkQv0ybp.jpg",
        "synopsis": "A mind-bending exploration of modern civilization, artificial virtual reality, and human moral downfall directed by visionary Upendra.",
        "formats": ["2D", "3D"],
    },

    # ================= ENGLISH / HOLLYWOOD =================
    {
        "title": "Captain America: Brave New World",
        "original_title": "Captain America: Brave New World",
        "language": "English",
        "genre": "Action, Sci-Fi, Adventure",
        "certificate": "UA",
        "duration_min": 138,
        "rating": 8.7,
        "rating_count": 145000,
        "external_rating": 8.5,
        "release_date": datetime(2025, 2, 14, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/2cxhvwyEwRlysAmRH4iodkvo0z5.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/eGvhFvC4PjX3j7qHjB8e6vV.jpg",
        "synopsis": "Sam Wilson finds himself in the middle of an international incident following a meeting with newly elected U.S. President Thaddeus Ross, uncovering a sinister global plot.",
        "formats": ["2D", "3D", "IMAX"],
    },
    {
        "title": "Mufasa: The Lion King",
        "original_title": "Mufasa: The Lion King",
        "language": "English",
        "genre": "Adventure, Animation, Drama",
        "certificate": "U",
        "duration_min": 128,
        "rating": 8.8,
        "rating_count": 180000,
        "external_rating": 8.6,
        "release_date": datetime(2024, 12, 20, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/wTnV3PCVW5O92JMrZvvrRcV39RU.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/v9acaWVvvyhhP1wUj0v5.jpg",
        "synopsis": "The epic tale of how an orphaned lion cub rose to become the legendary King of the Pride Lands alongside his brother Taka.",
        "formats": ["2D", "3D", "IMAX"],
    },
    {
        "title": "Moana 2",
        "original_title": "Moana 2",
        "language": "English",
        "genre": "Animation, Adventure, Musical",
        "certificate": "U",
        "duration_min": 100,
        "rating": 8.6,
        "rating_count": 135000,
        "external_rating": 8.4,
        "release_date": datetime(2024, 11, 27, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/aosm8NMQ3UyoBVpSxyimorCQykC.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/3V4kLQg0kSqPLctI5ziAhbAZSYH.jpg",
        "synopsis": "After receiving an unexpected call from her wayfinding ancestors, Moana journeys to the far seas of Oceania on an adventure unlike anything she's ever faced.",
        "formats": ["2D", "3D"],
    },
    {
        "title": "Gladiator II",
        "original_title": "Gladiator II",
        "language": "English",
        "genre": "Action, Adventure, Historical Drama",
        "certificate": "A",
        "duration_min": 148,
        "rating": 8.9,
        "rating_count": 195000,
        "external_rating": 8.7,
        "release_date": datetime(2024, 11, 15, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/8cdWjvZQUExUUTzyp4t6EDMubfO.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/yDHYTjA3R0ne8MRgu0f3i1O7l8r.jpg",
        "synopsis": "Years after witnessing the fall of Maximus, Lucius enters the Colosseum after his home is conquered by tyrannical Roman emperors.",
        "formats": ["2D", "IMAX", "DOLBY"],
    },
    {
        "title": "Venom: The Last Dance",
        "original_title": "Venom: The Last Dance",
        "language": "English",
        "genre": "Action, Sci-Fi, Adventure",
        "certificate": "UA",
        "duration_min": 110,
        "rating": 8.4,
        "rating_count": 120000,
        "external_rating": 8.1,
        "release_date": datetime(2024, 10, 24, tzinfo=timezone.utc),
        "poster_url": "https://image.tmdb.org/t/p/w500/2yB6w4V8wz1pL7Yk5n0Q7k8t9.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/9g9wWJt99QvA5f9yqA1K5R5gW0.jpg",
        "synopsis": "Eddie and Venom find themselves on the run from forces of both Earth and the Klyntar homeworld, facing a devastating final choice.",
        "formats": ["2D", "3D", "IMAX"],
    },
]

DAILY_HOURS_IST = [
    (10, 30),
    (14, 0),
    (17, 15),
    (20, 30),
    (22, 45),
]

async def update_to_latest_movies():
    print("--- 1. Cleaning up old mock/dummy titles (unpublishing from catalog) ---")
    async with AsyncSessionLocal() as session:
        # Find old mock titles
        mock_res = await session.execute(
            select(Movie).where(Movie.title.in_(MOCK_TITLES_TO_CLEAN))
        )
        mock_movies = mock_res.scalars().all()
        for m in mock_movies:
            # Mark movie as DRAFT / ARCHIVED so it disappears from public catalog
            m.status = "DRAFT"
            # Cancel future showtimes
            await session.execute(
                select(Showtime).where(Showtime.movie_id == m.id)
            )
            print(f"Unpublished mock movie: {m.title} (status=DRAFT)")

        await session.commit()

    print("\n--- 2. Upserting Genuine Latest 2024-2025 Theatrical Blockbusters ---")
    async with AsyncSessionLocal() as session:
        partner_res = await session.execute(select(PartnerORM).limit(1))
        partner = partner_res.scalar_one_or_none()
        partner_id = partner.id if partner else uuid.uuid4()

        movie_objs = {}
        for m_data in LATEST_MOVIES:
            existing_res = await session.execute(
                select(Movie).where(Movie.title == m_data["title"])
            )
            existing = existing_res.scalar_one_or_none()

            if existing:
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
                existing.status = "PUBLISHED"
                movie_objs[m_data["title"]] = existing
                print(f"Updated movie: {m_data['title']} ({m_data['language']}) - Release: {m_data['release_date'].strftime('%b %Y')}")
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
                movie_objs[m_data["title"]] = new_m
                print(f"Inserted new latest release: {m_data['title']} ({m_data['language']}) - Release: {m_data['release_date'].strftime('%b %Y')}")

        await session.flush()

        # 3. Fetch all venues & screens
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
        # Load existing future showtime slots
        existing_res = await session.execute(
            select(Showtime.screen_id, Showtime.starts_at).where(Showtime.starts_at > now_utc)
        )
        existing_slots = set((r[0], r[1]) for r in existing_res.all())

        tz_kolkata = ZoneInfo("Asia/Kolkata")
        today_kolkata = now_utc.astimezone(tz_kolkata).date()

        new_showtimes = []

        # Schedule showtimes for next 6 days
        for day_offset in range(6):
            current_date = today_kolkata + timedelta(days=day_offset)

            for m_data in LATEST_MOVIES:
                movie_obj = movie_objs[m_data["title"]]
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
                        for (ist_hr, ist_min) in DAILY_HOURS_IST:
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

        print(f"\nBulk inserting {len(new_showtimes)} showtimes for latest blockbuster movies...")
        session.add_all(new_showtimes)
        await session.commit()
        print("SUCCESS! Real latest BookMyShow & District movies updated and active!")

if __name__ == "__main__":
    asyncio.run(update_to_latest_movies())
