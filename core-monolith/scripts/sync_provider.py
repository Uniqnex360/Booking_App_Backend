# import asyncio
# import os
# import sys
# import uuid
# import httpx
# from datetime import datetime
# from pathlib import Path
# from datetime import datetime,timezone

# sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# from app.core.database import AsyncSessionLocal
# import app.auth.models
# import app.partner.models
# import app.event.models
# import app.movie.models
# from app.auth.models import User
# from app.partner.models import PartnerORM
# from app.movie.models import Venue, Screen, Movie, Showtime
# from app.shared.providers.registry import ProviderRegistryModel
# from sqlalchemy import select, update

# PVR_URL = os.getenv("PVR_BASE_URL", "https://pvr-backend-pejx.onrender.com").rstrip("/")
# PVR_EMAIL = os.getenv("PVR_ADMIN_EMAIL", "demo@pvr.local")
# PVR_PASSWORD = os.getenv("PVR_ADMIN_PASSWORD", "demo1234")

# POSTER_MAP = {
#     "i am game": "https://i.pinimg.com/1200x/c7/a8/58/c7a858e124a8da21b34624689fae49b2.jpg",
#     "the final whistle": "https://i.pinimg.com/736x/b2/a3/18/b2a31878a8498a21aa582d78094f775c.jpg",
# }


# async def sync_production():
#     print(f"1. Connecting to PVR at: {PVR_URL}")
#     async with httpx.AsyncClient(timeout=30.0) as client:
#         try:
#             login_resp = await client.post(
#                 f"{PVR_URL}/v1/auth/login",
#                 json={"email": PVR_EMAIL, "password": PVR_PASSWORD},
#             )
#             pvr_token = login_resp.json().get("token") if login_resp.status_code == 200 else None

#             st_resp = await client.get(f"{PVR_URL}/v1/showtimes")
#             pvr_showtimes = st_resp.json()
#         except Exception as e:
#             print(f"Error connecting to PVR ({PVR_URL}): {e}")
#             return

#     if not pvr_showtimes:
#         print("No showtimes returned from PVR.")
#         return

#     print(f"2. Fetched {len(pvr_showtimes)} live showtime(s) from PVR.")

#     async with AsyncSessionLocal() as session:
#         # --- Partner (unchanged) ---
#         partner_query = await session.execute(
#             select(PartnerORM).where(PartnerORM.business_name == "PVR Cinemas Ltd")
#         )
#         partner_orm = partner_query.scalar_one_or_none()

#         if not partner_orm:
#             partner_user_id = uuid.uuid4()
#             partner_id = uuid.uuid4()
#             partner_user = User(
#                 id=partner_user_id,
#                 full_name="PVR Cinemas Partner",
#                 email="partner_pvr@vignette.local",
#                 password_hash="system_managed",
#                 role="PARTNER",
#                 is_active=True,
#             )
#             session.add(partner_user)
#             await session.flush()

#             partner_orm = PartnerORM(
#                 id=partner_id,
#                 user_id=partner_user_id,
#                 business_name="PVR Cinemas Ltd",
#                 partner_type="event_organiser",
#                 contact_name="PVR Manager",
#                 contact_phone="9876543210",
#                 city="Kochi",
#                 status="APPROVED",
#             )
#             session.add(partner_orm)
#             await session.flush()
#         else:
#             partner_id = partner_orm.id

#         # --- Provider (unchanged) ---
#         provider_query = await session.execute(
#             select(ProviderRegistryModel).where(ProviderRegistryModel.name.ilike("%pvr%"))
#         )
#         provider = provider_query.scalar_one_or_none()
#         if not provider:
#             provider = ProviderRegistryModel(
#                 id=uuid.uuid4(),
#                 name="PVR Provider",
#                 base_url=PVR_URL,
#                 auth_token_ref=pvr_token,
#                 hold_ttl_seconds=600,
#                 enabled=True,
#                 partner_id=partner_id,
#             )
#             session.add(provider)
#             await session.flush()
#         else:
#             provider.base_url = PVR_URL
#             if pvr_token:
#                 provider.auth_token_ref = pvr_token
#             await session.flush()

#         # --- NEW: build venue + screen maps keyed by (cinema_name, city, screen_name) ---

#         venues_by_key: dict[tuple[str, str], Venue] = {}
#         screens_by_key: dict[tuple[str, str, str], Screen] = {}

#         for st in pvr_showtimes:
#             cinema_name = st.get("cinema_name") or "Unknown Cinema"
#             city = st.get("city") or "Kochi"
#             screen_name = st.get("screen_name") or "Screen 1"

#             vkey = (cinema_name, city)
#             if vkey not in venues_by_key:
#                 venue = (await session.execute(
#                     select(Venue).where(Venue.name == cinema_name, Venue.city == city)
#                 )).scalar_one_or_none()
#                 if not venue:
#                     venue = Venue(
#                         id=uuid.uuid4(),
#                         name=cinema_name,
#                         city=city,
#                         address=None,
#                         timezone="Asia/Kolkata",
#                         partner_id=partner_id,
#                     )
#                     session.add(venue)
#                     await session.flush()
#                 venues_by_key[vkey] = venue

#             skey = (cinema_name, city, screen_name)
#             if skey not in screens_by_key:
#                 venue = venues_by_key[vkey]
#                 screen = (await session.execute(
#                     select(Screen).where(
#                         Screen.venue_id == venue.id,
#                         Screen.name == screen_name,
#                     )
#                 )).scalar_one_or_none()
#                 if not screen:
#                     screen = Screen(
#                         id=uuid.uuid4(),
#                         venue_id=venue.id,
#                         name=screen_name,
#                         total_seats=0,
#                     )
#                     session.add(screen)
#                     await session.flush()
#                 screens_by_key[skey] = screen

#         # --- Cancel stale showtimes ---
#         current_pvr_ids = [st["id"] for st in pvr_showtimes]
#         await session.execute(
#             update(Showtime)
#             .where(
#                 Showtime.provider_id == provider.id,
#                 Showtime.provider_showtime_ref.notin_(current_pvr_ids),
#             )
#             .values(status="CANCELLED")
#         )

#         # --- Upsert movies + showtimes ---
#         synced = 0
#         for st in pvr_showtimes:
#             title = st["movie_title"]
#             title_clean = title.lower().strip()
#             poster_url = (
#                 st.get("poster_url")
#                 or POSTER_MAP.get(title_clean)
#                 or "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=800&auto=format&fit=crop&q=80"
#             )

#             movie_q = await session.execute(select(Movie).where(Movie.title == title))
#             movie = movie_q.scalar_one_or_none()
#             if not movie:
#                 release_year = st.get("release_year")
#                 release_date = (
#                     datetime(release_year, 1, 1, tzinfo=timezone.utc)
#                     if release_year else None
#                 )
#                 movie = Movie(
#                     id=uuid.uuid4(),
#                     title=title,
#                     language=st.get("language", "Malayalam"),
#                     duration_min=st.get("duration_min", 150),
#                     certificate=st.get("certificate", "UA"),
#                     status="PUBLISHED",
#                     partner_id=partner_id,
#                     poster_url=poster_url,
#                     release_date=release_date, 
#                     genre=st.get("genre"),  
#                     synopsis=f"Now showing at PVR Cinemas: {title}",
#                 )
#                 session.add(movie)
#                 await session.flush()
#             else:
#                 movie.poster_url = poster_url
#                 movie.genre = st.get("genre") 
#                 release_year = st.get("release_year")
#                 if release_year:
#                     movie.release_date = datetime(release_year, 1, 1, tzinfo=timezone.utc)
#                 await session.flush()

#             cinema_name = st.get("cinema_name") or "Unknown Cinema"
#             city = st.get("city") or "Kochi"
#             screen_name = st.get("screen_name") or "Screen 1"
#             screen = screens_by_key[(cinema_name, city, screen_name)]

#             starts_at_dt = datetime.fromisoformat(st["starts_at"].replace("Z", "+00:00"))

#             existing_st = (await session.execute(
#                 select(Showtime).where(Showtime.provider_showtime_ref == st["id"])
#             )).scalar_one_or_none()

#             if not existing_st:
#                 new_st = Showtime(
#                     id=uuid.uuid4(),
#                     screen_id=screen.id,
#                     movie_id=movie.id,
#                     starts_at=starts_at_dt,
#                     language=st.get("language", "Malayalam"),
#                     format="2D",
#                     status="ACTIVE",
#                     partner_id=partner_id,
#                     provider_id=provider.id,
#                     provider_showtime_ref=st["id"],
#                 )
#                 session.add(new_st)
#                 synced += 1
#             else:
#                 existing_st.screen_id = screen.id
#                 existing_st.starts_at = starts_at_dt
#                 existing_st.provider_id = provider.id
#                 existing_st.status = "ACTIVE"
#                 synced += 1

#         await session.commit()
#         print(f"Synced {synced} showtime(s). Venues: {len(venues_by_key)}, Screens: {len(screens_by_key)}.")


# if __name__ == "__main__":
#     asyncio.run(sync_production())
"""
Sync showtimes from all enabled providers into Vyhbz.

Reads provider_registry rows, fetches /v1/showtimes from each enabled
provider's base_url, and upserts venues/screens/movies/showtimes tagged
with that provider's id. Idempotent.
"""
import asyncio
import sys
import uuid
import httpx
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update, func

from app.core.database import AsyncSessionLocal
import app.auth.models
import app.partner.models
import app.event.models
import app.movie.models
from app.auth.models import User
from app.partner.models import PartnerORM
from app.movie.models import Venue, Screen, Movie, Showtime
from app.shared.providers.registry import ProviderRegistryModel


DEFAULT_POSTER = (
    "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba"
    "?w=800&auto=format&fit=crop&q=80"
)

CURATED_POSTER_BANNER_MAP: dict[str, dict[str, str]] = {
    "marco": {
        "poster_url": "https://image.tmdb.org/t/p/original/6Nj8Y1A9lcReqZZvRHOSiO3iTl6.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/a6RkQIOZ6wThQOEDv6lHsfH53hD.jpg",
    },
    "amaran": {
        "poster_url": "https://image.tmdb.org/t/p/original/eCB06m1KUGilEOlIzb40nkQhVY0.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/7cNE2qydew1c8fqnlhWjkE3DHc2.jpg",
    },
    "deadpool & wolverine": {
        "poster_url": "https://image.tmdb.org/t/p/original/8cdWjvZQUExUUTzyp4t6EDMubfO.jpg",
        "banner_url": "https://image.tmdb.org/t/p/original/by8z9Fe8y7p4jo2YlW2SZDnptyT.jpg",
    },
}

CURATED_MOVIE_CAST_CREW: dict[str, dict[str, list[dict]]] = {
    "aavesham": {
        "cast": [
            {"name": "Fahadh Faasil", "role": "Ranga", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/ba/Fahadh_Faasil_2019.jpg/330px-Fahadh_Faasil_2019.jpg"},
            {"name": "Hipzster", "role": "Aju", "photo_url": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=300&auto=format&fit=crop&q=80"},
            {"name": "Mithun Jai Shankar", "role": "Bibi", "photo_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80"},
            {"name": "Roshan Shanavas", "role": "Shanthan", "photo_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=300&auto=format&fit=crop&q=80"},
            {"name": "Sajin Gopu", "role": "Amban", "photo_url": "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=300&auto=format&fit=crop&q=80"},
            {"name": "Mansoor Ali Khan", "role": "Reddy", "photo_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=300&auto=format&fit=crop&q=80"},
            {"name": "Ashish Vidyarthi", "role": "Executive Director", "photo_url": "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Jithu Madhavan", "role": "Director & Writer", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
            {"name": "Nazriya Nazim", "role": "Producer", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/20/Nazriya_Nazim_at_neram_audio_launch.jpg/330px-Nazriya_Nazim_at_neram_audio_launch.jpg"},
            {"name": "Anwar Rasheed", "role": "Producer", "photo_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80"},
            {"name": "Sushin Shyam", "role": "Musician", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/Sushin_Shyam.jpg/330px-Sushin_Shyam.jpg"},
            {"name": "Sameer Thahir", "role": "Cinematographer", "photo_url": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=300&auto=format&fit=crop&q=80"},
            {"name": "Vivek Harshan", "role": "Editor", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "manjummel boys": {
        "cast": [
            {"name": "Soubin Shahir", "role": "Kuttan", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/79/Soubin_Shahir_2019.jpg/330px-Soubin_Shahir_2019.jpg"},
            {"name": "Sreenath Bhasi", "role": "Subhash", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/74/Sreenath_Bhasi_latest_.jpg/330px-Sreenath_Bhasi_latest_.jpg"},
            {"name": "Balu Varghese", "role": "Sixen", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/b/bd/Balu_Varghese_at_SBCE.jpg/330px-Balu_Varghese_at_SBCE.jpg"},
            {"name": "Ganapathi", "role": "Krishnakumar", "photo_url": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=300&auto=format&fit=crop&q=80"},
            {"name": "Jean Paul Lal", "role": "Siju David", "photo_url": "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=300&auto=format&fit=crop&q=80"},
            {"name": "Deepak Parambol", "role": "Sudhi", "photo_url": "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=300&auto=format&fit=crop&q=80"},
            {"name": "Abhiram Radhakrishnan", "role": "Anil", "photo_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Chidambaram", "role": "Director & Writer", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
            {"name": "Babu Shahir", "role": "Producer", "photo_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=300&auto=format&fit=crop&q=80"},
            {"name": "Shawn Antony", "role": "Producer", "photo_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80"},
            {"name": "Sushin Shyam", "role": "Musician", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/Sushin_Shyam.jpg/330px-Sushin_Shyam.jpg"},
            {"name": "Shyju Khalid", "role": "Cinematographer", "photo_url": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=300&auto=format&fit=crop&q=80"},
            {"name": "Vivek Harshan", "role": "Editor", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "bramayugam": {
        "cast": [
            {"name": "Mammootty", "role": "Kodumon Potti", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/50/Mammootty%2C_2022.jpg/330px-Mammootty%2C_2022.jpg"},
            {"name": "Arjun Ashokan", "role": "Thevan", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/52/Arjun_Ashokan_2026.jpg/330px-Arjun_Ashokan_2026.jpg"},
            {"name": "Sidharth Bharathan", "role": "The Cook", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/Sidharth_Bharathan_2017.jpg/330px-Sidharth_Bharathan_2017.jpg"},
            {"name": "Amalda Liz", "role": "Yakshi", "photo_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300&auto=format&fit=crop&q=80"},
            {"name": "Manikandan R. Achari", "role": "Chathan", "photo_url": "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Rahul Sadasivan", "role": "Director & Writer", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/55/RahulSpic_2024_-_jpg_%28cropped%29.jpg/330px-RahulSpic_2024_-_jpg_%28cropped%29.jpg"},
            {"name": "Chakravarthy Ramachandra", "role": "Producer", "photo_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=300&auto=format&fit=crop&q=80"},
            {"name": "S. Sashikanth", "role": "Producer", "photo_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80"},
            {"name": "Christo Xavier", "role": "Musician", "photo_url": "https://images.unsplash.com/photo-1513956589380-bad6acb9b9d4?w=300&auto=format&fit=crop&q=80"},
            {"name": "Shehnad Jalal", "role": "Cinematographer", "photo_url": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=300&auto=format&fit=crop&q=80"},
            {"name": "Shafique Mohamed Ali", "role": "Editor", "photo_url": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "kingdom": {
        "cast": [
            {"name": "Vijay Deverakonda", "role": "Suriya", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/8/84/Vijay_Devarakonda_snapped_during_Liger_promotions.jpg"},
            {"name": "Bhagyashri Borse", "role": "Maya", "photo_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300&auto=format&fit=crop&q=80"},
            {"name": "Satyadev Kancharana", "role": "Vikram", "photo_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80"},
            {"name": "Jagapathi Babu", "role": "Dharma", "photo_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=300&auto=format&fit=crop&q=80"},
            {"name": "Sunil", "role": "Raghava", "photo_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Gowtam Tinnanuri", "role": "Director & Writer", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
            {"name": "Naga Vamsi S.", "role": "Producer", "photo_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80"},
            {"name": "Anirudh Ravichander", "role": "Musician", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d4/Anirudh_Ravichander_at_Audi_Ritz_Style_Awards_2017_%28cropped%29.jpg/330px-Anirudh_Ravichander_at_Audi_Ritz_Style_Awards_2017_%28cropped%29.jpg"},
            {"name": "Girish Gangadharan", "role": "Cinematographer", "photo_url": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=300&auto=format&fit=crop&q=80"},
            {"name": "Navin Nooli", "role": "Editor", "photo_url": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "vaazha": {
        "cast": [
            {"name": "Jeemon George", "role": "Ajo", "photo_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80"},
            {"name": "Hashir", "role": "Vishnu", "photo_url": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=300&auto=format&fit=crop&q=80"},
            {"name": "Alan", "role": "Moosa", "photo_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=300&auto=format&fit=crop&q=80"},
            {"name": "Vinayak", "role": "Vivek", "photo_url": "https://images.unsplash.com/photo-1522075469751-3a6694fb2f61?w=300&auto=format&fit=crop&q=80"},
            {"name": "Jagadish", "role": "Father", "photo_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=300&auto=format&fit=crop&q=80"},
            {"name": "Kottayam Nazeer", "role": "Principal", "photo_url": "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Anand Menen", "role": "Director", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
            {"name": "Vipin Das", "role": "Writer & Producer", "photo_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80"},
            {"name": "Ankit Menon", "role": "Musician", "photo_url": "https://images.unsplash.com/photo-1513956589380-bad6acb9b9d4?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "i am game": {
        "cast": [
            {"name": "Prithviraj Sukumaran", "role": "David Koshy", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/4/48/Prithviraj_at_Aiyyaa_event.jpg"},
            {"name": "Nayanthara", "role": "Ananya", "photo_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300&auto=format&fit=crop&q=80"},
            {"name": "Tovino Thomas", "role": "Neil", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3d/Tovino_Thomas_At_The_%E2%80%98Maari_2%E2%80%99_Press_Meet.jpg/330px-Tovino_Thomas_At_The_%E2%80%98Maari_2%E2%80%99_Press_Meet.jpg"},
            {"name": "Indrajith Sukumaran", "role": "Roy", "photo_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=300&auto=format&fit=crop&q=80"},
            {"name": "Suraj Venjaramoodu", "role": "Mathew", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/82/Photo_of_Suraj_captured_by_Ujwal_Rajeev.jpg/330px-Photo_of_Suraj_captured_by_Ujwal_Rajeev.jpg"},
        ],
        "crew": [
            {"name": "Jeethu Joseph", "role": "Director", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/78/Jeethu_Joseph_%28director%29_%282019%29.jpg/330px-Jeethu_Joseph_%28director%29_%282019%29.jpg"},
            {"name": "Antony Perumbavoor", "role": "Producer", "photo_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80"},
            {"name": "Jakes Bejoy", "role": "Musician", "photo_url": "https://images.unsplash.com/photo-1513956589380-bad6acb9b9d4?w=300&auto=format&fit=crop&q=80"},
            {"name": "Satheesh Kurup", "role": "Cinematographer", "photo_url": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "the final whistle": {
        "cast": [
            {"name": "Christian Bale", "role": "Coach Marcus", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/Christian_Bale-7837.jpg/330px-Christian_Bale-7837.jpg"},
            {"name": "Florence Pugh", "role": "Dr. Clara Evans", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Florence_Pugh_at_the_2024_Toronto_International_Film_Festival_13_%28cropped_2_%E2%80%93_color_adjusted%29.jpg/330px-Florence_Pugh_at_the_2024_Toronto_International_Film_Festival_13_%28cropped_2_%E2%80%93_color_adjusted%29.jpg"},
            {"name": "John Boyega", "role": "Leo Stone", "photo_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80"},
            {"name": "Woody Harrelson", "role": "General Vance", "photo_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Ridley Scott", "role": "Director", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/58/Ridley_Scott_At_BFI_-_BFI_Southbank_-_Saturday_4th_October_2025.jpg/330px-Ridley_Scott_At_BFI_-_BFI_Southbank_-_Saturday_4th_October_2025.jpg"},
            {"name": "Hans Zimmer", "role": "Musician", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2b/Hans-Zimmer-profile.jpg/330px-Hans-Zimmer-profile.jpg"},
        ],
    },
    "last whistle": {
        "cast": [
            {"name": "Christian Bale", "role": "Coach Marcus", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/0a/Christian_Bale-7837.jpg/330px-Christian_Bale-7837.jpg"},
            {"name": "Florence Pugh", "role": "Dr. Clara Evans", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/9/9e/Florence_Pugh_at_the_2024_Toronto_International_Film_Festival_13_%28cropped_2_%E2%80%93_color_adjusted%29.jpg/330px-Florence_Pugh_at_the_2024_Toronto_International_Film_Festival_13_%28cropped_2_%E2%80%93_color_adjusted%29.jpg"},
            {"name": "John Boyega", "role": "Leo Stone", "photo_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Ridley Scott", "role": "Director", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/5/58/Ridley_Scott_At_BFI_-_BFI_Southbank_-_Saturday_4th_October_2025.jpg/330px-Ridley_Scott_At_BFI_-_BFI_Southbank_-_Saturday_4th_October_2025.jpg"},
            {"name": "Hans Zimmer", "role": "Musician", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2b/Hans-Zimmer-profile.jpg/330px-Hans-Zimmer-profile.jpg"},
        ],
    },
    "avengers: endgame encore": {
        "cast": [
            {"name": "Robert Downey Jr.", "role": "Tony Stark / Iron Man", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a9/RobertDowneyJr-byPhilipRomano7_%28cropped%29.jpg/330px-RobertDowneyJr-byPhilipRomano7_%28cropped%29.jpg"},
            {"name": "Chris Evans", "role": "Steve Rogers / Captain America", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Chris_Evans_at_the_2025_Toronto_International_Film_Festival_%28cropped%29.jpg/330px-Chris_Evans_at_the_2025_Toronto_International_Film_Festival_%28cropped%29.jpg"},
            {"name": "Scarlett Johansson", "role": "Natasha Romanoff / Black Widow", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ad/Scarlett_Johansson-8588.jpg/330px-Scarlett_Johansson-8588.jpg"},
            {"name": "Chris Hemsworth", "role": "Thor", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/8/86/Chris_Hemsworth_-_Crime_101.jpg/330px-Chris_Hemsworth_-_Crime_101.jpg"},
            {"name": "Mark Ruffalo", "role": "Bruce Banner / Hulk", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/11/Mark_Ruffalo_%2836201774756%29_%28cropped%29.jpg/330px-Mark_Ruffalo_%2836201774756%29_%28cropped%29.jpg"},
            {"name": "Paul Rudd", "role": "Scott Lang / Ant-Man", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/31/Paul_Rudd_and_Kate_Mara_at_the_2024_Toronto_International_Film_Festival_8_%28cropped%29.jpg/330px-Paul_Rudd_and_Kate_Mara_at_the_2024_Toronto_International_Film_Festival_8_%28cropped%29.jpg"},
            {"name": "Benedict Cumberbatch", "role": "Doctor Strange", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/Benedict_Cumberbatch-67555.jpg/330px-Benedict_Cumberbatch-67555.jpg"},
            {"name": "Chadwick Boseman", "role": "T'Challa / Black Panther", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e8/Chadwick_Boseman_by_Gage_Skidmore_July_2017_%28cropped%29.jpg/330px-Chadwick_Boseman_by_Gage_Skidmore_July_2017_%28cropped%29.jpg"},
            {"name": "Tom Holland", "role": "Peter Parker / Spider-Man", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/18/TomHolland-byPhilipRomano.jpg/330px-TomHolland-byPhilipRomano.jpg"},
        ],
        "crew": [
            {"name": "Anthony & Joe Russo", "role": "Directors", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
            {"name": "Kevin Feige", "role": "Producer", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Kevin_Feige_by_Gage_Skidmore.jpg/330px-Kevin_Feige_by_Gage_Skidmore.jpg"},
            {"name": "Alan Silvestri", "role": "Musician", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/2/25/Alan_Silvestri_2009.jpg/330px-Alan_Silvestri_2009.jpg"},
            {"name": "Trent Opaloch", "role": "Cinematographer", "photo_url": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "pradhama drishtiya kuttakkar": {
        "cast": [
            {"name": "Parvathy Thiruvothu", "role": "Actor", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/da/Actress_Parvathi.jpg/330px-Actress_Parvathi.jpg"},
            {"name": "Mathew Thomas", "role": "Actor", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6a/Mathew_Thomas_2020.jpg/330px-Mathew_Thomas_2020.jpg"},
            {"name": "Sidharth Bharathan", "role": "Actor", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/6/62/Sidharth_Bharathan_2017.jpg/330px-Sidharth_Bharathan_2017.jpg"},
            {"name": "Unnimaya Prasad", "role": "Actor", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Unnimaya_Prasad.jpg/330px-Unnimaya_Prasad.jpg"},
            {"name": "Vijayaraghavan", "role": "Actor", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/ef/Vijayaraghavan.jpg/330px-Vijayaraghavan.jpg"},
            {"name": "Azees Nedumangad", "role": "Actor", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/d/d5/Ratheesh_Raghunandan_and_Azeez_Nedumangadu.jpg/330px-Ratheesh_Raghunandan_and_Azeez_Nedumangadu.jpg"},
        ],
        "crew": [
            {"name": "Shahad Nilambur", "role": "Director", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
            {"name": "Arjun Selva", "role": "Producer", "photo_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80"},
            {"name": "P. S. Subramanian", "role": "Writer", "photo_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?w=300&auto=format&fit=crop&q=80"},
            {"name": "Mujeeb Majeed", "role": "Musician", "photo_url": "https://images.unsplash.com/photo-1513956589380-bad6acb9b9d4?w=300&auto=format&fit=crop&q=80"},
            {"name": "Roby Varghese Raj", "role": "Cinematographer", "photo_url": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=300&auto=format&fit=crop&q=80"},
            {"name": "Chaman Chacko", "role": "Editor", "photo_url": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "marco": {
        "cast": [
            {"name": "Unni Mukundan", "role": "Marco Jr.", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cd/Unni_Mukundan_at_Ira_Audio_Launch.jpg/330px-Unni_Mukundan_at_Ira_Audio_Launch.jpg"},
            {"name": "Jagadish", "role": "Tony", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Jagadish_2019.jpg/330px-Jagadish_2019.jpg"},
            {"name": "Siddique", "role": "George", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/3/30/Siddique_Actor.jpg/330px-Siddique_Actor.jpg"},
            {"name": "Kabir Duhan Singh", "role": "Isaac", "photo_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80"},
            {"name": "Anson Paul", "role": "Peter", "photo_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Haneef Adeni", "role": "Director & Writer", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
            {"name": "Shareef Muhammed", "role": "Producer", "photo_url": "https://images.unsplash.com/photo-1560250097-0b93528c311a?w=300&auto=format&fit=crop&q=80"},
            {"name": "Ravi Basrur", "role": "Musician", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/0/02/Sushin_Shyam.jpg/330px-Sushin_Shyam.jpg"},
            {"name": "Chandru Selvaraj", "role": "Cinematographer", "photo_url": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=300&auto=format&fit=crop&q=80"},
            {"name": "Shameer Muhammed", "role": "Editor", "photo_url": "https://images.unsplash.com/photo-1539571696357-5a69c17a67c6?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "amaran": {
        "cast": [
            {"name": "Sivakarthikeyan", "role": "Major Mukund Varadarajan", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/7b/Sivakarthikeyan_at_Doctor_success_meet.jpg/330px-Sivakarthikeyan_at_Doctor_success_meet.jpg"},
            {"name": "Sai Pallavi", "role": "Indhu Rebecca Varghese", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e0/Sai_Pallavi_at_Gargi_press_meet.jpg/330px-Sai_Pallavi_at_Gargi_press_meet.jpg"},
            {"name": "Bhuvan Arora", "role": "Sepoy Vikram Singh", "photo_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80"},
            {"name": "Rahul Bose", "role": "Col. Amit Singh Shekhawat", "photo_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Rajkumar Periasamy", "role": "Director & Writer", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
            {"name": "Kamal Haasan", "role": "Producer", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/a/a2/Kamal_Haasan_at_the_Vikram_Press_Meet_%28cropped%29.jpg/330px-Kamal_Haasan_at_the_Vikram_Press_Meet_%28cropped%29.jpg"},
            {"name": "G. V. Prakash Kumar", "role": "Musician", "photo_url": "https://images.unsplash.com/photo-1513956589380-bad6acb9b9d4?w=300&auto=format&fit=crop&q=80"},
            {"name": "CH Sai", "role": "Cinematographer", "photo_url": "https://images.unsplash.com/photo-1501196354995-cbb51c65aaea?w=300&auto=format&fit=crop&q=80"},
        ],
    },
    "deadpool & wolverine": {
        "cast": [
            {"name": "Ryan Reynolds", "role": "Wade Wilson / Deadpool", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/14/Deadpool_2_Japan_Premiere_Red_Carpet_Ryan_Reynolds_%28cropped%29.jpg/330px-Deadpool_2_Japan_Premiere_Red_Carpet_Ryan_Reynolds_%28cropped%29.jpg"},
            {"name": "Hugh Jackman", "role": "Logan / Wolverine", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/7/77/Logan_Japan_Premiere_Red_Carpet_Hugh_Jackman_%28cropped%29.jpg/330px-Logan_Japan_Premiere_Red_Carpet_Hugh_Jackman_%28cropped%29.jpg"},
            {"name": "Emma Corrin", "role": "Cassandra Nova", "photo_url": "https://images.unsplash.com/photo-1534528741775-53994a69daeb?w=300&auto=format&fit=crop&q=80"},
            {"name": "Matthew Macfadyen", "role": "Mr. Paradox", "photo_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?w=300&auto=format&fit=crop&q=80"},
        ],
        "crew": [
            {"name": "Shawn Levy", "role": "Director & Producer", "photo_url": "https://images.unsplash.com/photo-1519085360753-af0119f7cbe7?w=300&auto=format&fit=crop&q=80"},
            {"name": "Kevin Feige", "role": "Producer", "photo_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/1/1a/Kevin_Feige_by_Gage_Skidmore.jpg/330px-Kevin_Feige_by_Gage_Skidmore.jpg"},
            {"name": "Rob Simonsen", "role": "Musician", "photo_url": "https://images.unsplash.com/photo-1513956589380-bad6acb9b9d4?w=300&auto=format&fit=crop&q=80"},
        ],
    },
}


def resolve_movie_cast_and_crew(
    title: str,
    raw_cast: list | None = None,
    raw_crew: list | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Check if the movie has cast and crew from the provider.
    If not, resolve from curated catalog with authentic names and pictures.
    """
    valid_cast = [
        c for c in (raw_cast or [])
        if isinstance(c, dict) and c.get("name")
    ]
    valid_crew = [
        c for c in (raw_crew or [])
        if isinstance(c, dict) and c.get("name")
    ]
    if valid_cast and valid_crew:
        return valid_cast, valid_crew

    t_clean = (title or "").lower().strip()
    curated = CURATED_MOVIE_CAST_CREW.get(t_clean)
    if not curated:
        for k, v in CURATED_MOVIE_CAST_CREW.items():
            if k in t_clean or t_clean in k:
                curated = v
                break

    if curated:
        cast = valid_cast if valid_cast else curated.get("cast", [])
        crew = valid_crew if valid_crew else curated.get("crew", [])
        return cast, crew

    return valid_cast or [], valid_crew or []


async def _ensure_partner(session) -> PartnerORM:
    partner = (await session.execute(
        select(PartnerORM).where(PartnerORM.business_name == "PVR Cinemas Ltd")
    )).scalar_one_or_none()
    if partner:
        return partner

    partner_user_id = uuid.uuid4()
    partner_id = uuid.uuid4()

    session.add(User(
        id=partner_user_id,
        full_name="Aggregated Cinemas Partner",
        email="partner_agg@vignette.local",
        password_hash="system_managed",
        role="PARTNER",
        is_active=True,
    ))
    await session.flush()

    partner = PartnerORM(
        id=partner_id,
        user_id=partner_user_id,
        business_name="PVR Cinemas Ltd",
        partner_type="event_organiser",
        contact_name="Sync Manager",
        contact_phone="9876543210",
        city="Kochi",
        status="APPROVED",
    )
    session.add(partner)
    await session.flush()
    return partner


async def _fetch_showtimes(client: httpx.AsyncClient, base_url: str) -> list[dict]:
    resp = await client.get(f"{base_url.rstrip('/')}/v1/showtimes")
    resp.raise_for_status()
    return resp.json()
async def _sync_one_provider(
    session,
    client: httpx.AsyncClient,
    provider: ProviderRegistryModel,
    partner_id: uuid.UUID,
) -> dict:
    """Returns {'venues': n, 'screens': n, 'showtimes': n, 'cancelled': n}"""
    base = provider.base_url.rstrip("/")
    print(f"  -> {provider.name} @ {base}")

    try:
        pvr_showtimes = await _fetch_showtimes(client, base)
    except Exception as exc:
        print(f"     FETCH FAILED: {exc} — skipping provider, no rows touched")
        return {
            "venues": 0, "screens": 0, "showtimes": 0, "cancelled": 0,
            "error": str(exc), "skipped": True,
        }

    if not pvr_showtimes:
        print("     EMPTY RESPONSE — skipping provider, no rows touched")
        return {
            "venues": 0, "screens": 0, "showtimes": 0, "cancelled": 0,
            "skipped": True, "reason": "empty_response",
        }

    # --- Build venue + screen maps scoped to this provider ---
    venues_by_key: dict[tuple[str, str], Venue] = {}
    screens_by_key: dict[tuple[str, str, str], Screen] = {}

    for st in pvr_showtimes:
        cinema_name = st.get("cinema_name") or "Unknown Cinema"
        city = st.get("city") or "Kochi"
        screen_name = st.get("screen_name") or "Screen 1"

        vkey = (cinema_name, city)
        if vkey not in venues_by_key:
            venue = (await session.execute(
                select(Venue).where(
                    Venue.name == cinema_name,
                    Venue.city == city,
                    Venue.partner_id == partner_id,
                )
            )).scalar_one_or_none()
            if not venue:
                venue = Venue(
                    id=uuid.uuid4(),
                    name=cinema_name,
                    city=city,
                    address=None,
                    timezone="Asia/Kolkata",
                    partner_id=partner_id,
                )
                session.add(venue)
                await session.flush()
            venues_by_key[vkey] = venue

        skey = (cinema_name, city, screen_name)
        if skey not in screens_by_key:
            venue = venues_by_key[vkey]
            screen = (await session.execute(
                select(Screen).where(
                    Screen.venue_id == venue.id,
                    Screen.name == screen_name,
                )
            )).scalar_one_or_none()
            if not screen:
                screen = Screen(
                    id=uuid.uuid4(),
                    venue_id=venue.id,
                    name=screen_name,
                    total_seats=0,
                )
                session.add(screen)
                await session.flush()
            screens_by_key[skey] = screen

    # --- Guarded cancellation ---
    #
    # CANCELLATION IS ONLY VALID WHEN ABSENCE IS CONFIRMED.
    # We confirmed a successful, non-empty fetch above. But to guard against
    # partial responses from a cold Render instance or a mid-stream timeout,
    # we refuse to cancel more than 20% of the provider's currently-active
    # showtimes in one sync. Anything more indicates a fetch problem, not a
    # real schedule change.
    current_ids = [st["id"] for st in pvr_showtimes]

    now = datetime.now(timezone.utc)

    live_count = (await session.execute(
        select(func.count()).select_from(Showtime).where(
            Showtime.provider_id == provider.id,
            Showtime.status == "ACTIVE",
            Showtime.starts_at > now,
        )
    )).scalar() or 0

    prospective_cancel_count = (await session.execute(
        select(func.count()).select_from(Showtime).where(
            Showtime.provider_id == provider.id,
            Showtime.status == "ACTIVE",
            Showtime.starts_at > now,
            Showtime.provider_showtime_ref.notin_(current_ids),
        )
    )).scalar() or 0

    if live_count > 0 and prospective_cancel_count > max(5, int(live_count * 0.2)):
        print(
            f"     CANCELLATION REFUSED: would cancel {prospective_cancel_count} of "
            f"{live_count} live showtimes "
            f"({prospective_cancel_count * 100 // live_count}%). "
            f"Threshold is 20%. Treating as a fetch problem, no rows touched."
        )
        return {
            "venues": 0, "screens": 0, "showtimes": 0, "cancelled": 0,
            "skipped": True, "reason": "cancellation_threshold_exceeded",
            "would_have_cancelled": prospective_cancel_count,
        }

    cancel_result = await session.execute(
        update(Showtime)
        .where(
            Showtime.provider_id == provider.id,
            Showtime.provider_showtime_ref.notin_(current_ids),
        )
        .values(status="CANCELLED")
    )
    cancelled = cancel_result.rowcount or 0


    titles = {st["movie_title"] for st in pvr_showtimes}
    existing_movies = (await session.execute(
        select(Movie).where(Movie.title.in_(titles))
    )).scalars().all()
    movies_by_title = {m.title: m for m in existing_movies}

    existing_showtimes = (await session.execute(
        select(Showtime).where(Showtime.provider_showtime_ref.in_(current_ids))
    )).scalars().all()
    showtimes_by_ref = {s.provider_showtime_ref: s for s in existing_showtimes}

    new_movies: list[Movie] = []
    new_showtimes: list[Showtime] = []
    synced = 0

    for st in pvr_showtimes:
        title = st["movie_title"]
        t_clean = (title or "").lower().strip()
        curated_media = CURATED_POSTER_BANNER_MAP.get(t_clean, {})
        poster_url = st.get("poster_url") or curated_media.get("poster_url") or DEFAULT_POSTER
        banner_url = st.get("banner_url") or curated_media.get("banner_url")
        raw_lang = st.get("language") or "Malayalam"

        starts_at_dt = datetime.fromisoformat(st["starts_at"].replace("Z", "+00:00"))
        cinema_name = st.get("cinema_name") or "Unknown Cinema"
        city = st.get("city") or "Kochi"
        screen_name = st.get("screen_name") or "Screen 1"
        screen = screens_by_key[(cinema_name, city, screen_name)]

        # Determine individual screening language
        if "," in raw_lang:
            langs = [l.strip() for l in raw_lang.split(",") if l.strip()]
            idx = (starts_at_dt.hour + int(screen_name[-1] if screen_name[-1].isdigit() else 0)) % len(langs)
            screening_lang = langs[idx]
        else:
            screening_lang = raw_lang

        movie = movies_by_title.get(title)
        if not movie:
            release_year = st.get("release_year")
            release_date = (
                datetime(release_year, 1, 1, tzinfo=timezone.utc)
                if release_year else None
            )
            cast, crew = resolve_movie_cast_and_crew(title, st.get("cast"), st.get("crew"))
            movie = Movie(
                id=uuid.uuid4(),
                title=title,
                language=raw_lang,
                duration_min=st.get("duration_min", 150),
                certificate=st.get("certificate", "UA"),
                status="PUBLISHED",
                partner_id=partner_id,
                poster_url=poster_url,
                banner_url=banner_url,
                release_date=release_date,
                genre=st.get("genre"),
                synopsis=f"Now showing: {title}",
                cast_json=cast,
                crew_json=crew,
            )
            new_movies.append(movie)
            movies_by_title[title] = movie
        else:
            if poster_url and poster_url != DEFAULT_POSTER:
                movie.poster_url = poster_url
            if banner_url:
                movie.banner_url = banner_url
            if raw_lang:
                movie.language = raw_lang
            if st.get("certificate"):
                movie.certificate = st.get("certificate")
            movie.genre = st.get("genre")
            release_year = st.get("release_year")
            if release_year:
                movie.release_date = datetime(release_year, 1, 1, tzinfo=timezone.utc)
            # Only overwrite cast/crew if the provider actually sends them
            if st.get("cast"):
                movie.cast_json = st["cast"]
            elif not movie.cast_json:
                cast, _ = resolve_movie_cast_and_crew(title, None, None)
                if cast:
                    movie.cast_json = cast
            if st.get("crew"):
                movie.crew_json = st["crew"]
            elif not movie.crew_json:
                _, crew = resolve_movie_cast_and_crew(title, None, None)
                if crew:
                    movie.crew_json = crew

        existing_st = showtimes_by_ref.get(st["id"])
        if not existing_st:
            new_showtimes.append(Showtime(
                id=uuid.uuid4(),
                screen_id=screen.id,
                movie_id=movie.id,
                starts_at=starts_at_dt,
                language=screening_lang,
                format="2D",
                status="ACTIVE",
                partner_id=partner_id,
                provider_id=provider.id,
                provider_showtime_ref=st["id"],
            ))
        else:
            existing_st.screen_id = screen.id
            existing_st.starts_at = starts_at_dt
            existing_st.language = screening_lang
            existing_st.provider_id = provider.id
            existing_st.status = "ACTIVE"

        synced += 1

    # Flush new movies first so they get ids, then showtimes that reference them.
    if new_movies:
        session.add_all(new_movies)
        await session.flush()
    if new_showtimes:
        session.add_all(new_showtimes)
        await session.flush()

    # Expire past showtimes so they don't block the guard tomorrow.
    expired_result = await session.execute(
        update(Showtime)
        .where(
            Showtime.provider_id == provider.id,
            Showtime.status == "ACTIVE",
            Showtime.starts_at < now,
        )
        .values(status="CANCELLED")
    )
    expired = expired_result.rowcount or 0
    if expired:
        print(f"     expired {expired} past showtime(s)")

    return {
        "venues": len(venues_by_key),
        "screens": len(screens_by_key),
        "showtimes": synced,
        "cancelled": cancelled,
    }
async def sync_all_providers():
    print("=" * 60)
    print("Vyhbz provider sync")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=30.0) as client:
        async with AsyncSessionLocal() as session:
            partner = await _ensure_partner(session)

            providers = (await session.execute(
                select(ProviderRegistryModel)
                .where(ProviderRegistryModel.enabled == True)
                .order_by(ProviderRegistryModel.name)
            )).scalars().all()

            if not providers:
                print("No enabled providers in provider_registry. Nothing to do.")
                return

            print(f"Found {len(providers)} enabled provider(s):\n")

            total = {"venues": 0, "screens": 0, "showtimes": 0, "cancelled": 0}
            for p in providers:
                stats = await _sync_one_provider(session, client, p, partner.id)
                for k in total:
                    total[k] += stats.get(k, 0)

            await session.commit()

            print()
            print("=" * 60)
            print(
                f"Totals across {len(providers)} provider(s): "
                f"{total['venues']} venues, {total['screens']} screens, "
                f"{total['showtimes']} showtimes, {total['cancelled']} cancelled"
            )
            print("=" * 60)


if __name__ == "__main__":
    asyncio.run(sync_all_providers())   