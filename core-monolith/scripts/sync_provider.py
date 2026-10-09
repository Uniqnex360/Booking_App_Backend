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

CURATED_MOVIE_CAST_CREW: dict[str, dict[str, list[dict]]] = {
    "kingdom": {
        "cast": [
            {
                "name": "Vijay Deverakonda",
                "role": "Soori",
                "photo_url": "https://image.tmdb.org/t/p/w300/8oVIWyIoFUal8SJFnmCUtkkm1HP.jpg"
            },
            {
                "name": "Satyadev Kancharana",
                "role": "Siva",
                "photo_url": "https://image.tmdb.org/t/p/w300/uIf1HM99iDVf9vdJwXPMgggOHkA.jpg"
            },
            {
                "name": "Venkitesh V P",
                "role": "Murugan",
                "photo_url": "https://image.tmdb.org/t/p/w300/wX72uREcCwXiUIbZMpxtkHLoC2O.jpg"
            },
            {
                "name": "Bhagyashri Borse",
                "role": "Madhu",
                "photo_url": "https://image.tmdb.org/t/p/w300/3gVgbXl0YC1xxrFatf0pEkFbK4Q.jpg"
            },
            {
                "name": "Ronit Kamra",
                "role": "Jr Suri",
                "photo_url": "https://image.tmdb.org/t/p/w300/A90xgEIR02s85z5SzMlOUZ8z0YB.jpg"
            },
            {
                "name": "Baburaj",
                "role": "Odiyappan",
                "photo_url": "https://image.tmdb.org/t/p/w300/nuJ7GhTfuBrlGBWeMPIYr59O8kP.jpg"
            },
            {
                "name": "Ayyappa P. Sharma",
                "role": "Divi Bhairagi",
                "photo_url": None
            },
            {
                "name": "Bhanu Prakashan",
                "role": "Young Siva",
                "photo_url": None
            },
            {
                "name": "Sriram Reddy Polasane",
                "role": "David",
                "photo_url": None
            },
            {
                "name": "Manish Chaudhary",
                "role": "Jayaprakash",
                "photo_url": "https://image.tmdb.org/t/p/w300/1l4vmA0IJQLieebZWOOCAFu4ra6.jpg"
            }
        ],
        "crew": [
            {
                "name": "Suryadevara Naga Vamsi",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/hLJpBV45WFqS3sYxS3zmBhcHAoq.jpg"
            },
            {
                "name": "Gowtam Tinnanuri",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/yA5HYmJGGwMXqMRAXrzHbkJNAfv.jpg"
            },
            {
                "name": "Girish Gangadharan",
                "role": "Director of Photography",
                "photo_url": "https://image.tmdb.org/t/p/w300/l0prBtRT58P3uHVYPMivXnJwIFT.jpg"
            },
            {
                "name": "Naveen Nooli",
                "role": "Editor",
                "photo_url": "https://image.tmdb.org/t/p/w300/dTYIRplqzKtT6LB8uONcIcsJz6I.jpg"
            },
            {
                "name": "Sai Soujanya",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/apJYXLrq71B80HKyjYS1ksAx7ID.jpg"
            },
            {
                "name": "Anirudh Ravichander",
                "role": "Original Music Composer",
                "photo_url": "https://image.tmdb.org/t/p/w300/xKvlrZpRaXkm2K2ZiXpqgrEedUU.jpg"
            },
            {
                "name": "Jomon T. John",
                "role": "Director of Photography",
                "photo_url": "https://image.tmdb.org/t/p/w300/q8p2iKw928tQ7ssuHx7gsPQQG8N.jpg"
            }
        ]
    },
    "last whistle": {
        "cast": [
            {
                "name": "Christian Bale",
                "role": "Coach Marcus",
                "photo_url": "https://image.tmdb.org/t/p/w300/7Pxez9J8fuPd2Mn9kex13YALrCQ.jpg"
            },
            {
                "name": "Florence Pugh",
                "role": "Dr. Clara Evans",
                "photo_url": "https://image.tmdb.org/t/p/w300/2URrZb95t3kY6pLroKny3Enmabp.jpg"
            },
            {
                "name": "John Boyega",
                "role": "Leo Stone",
                "photo_url": "https://image.tmdb.org/t/p/w300/3153CfpgZQXTzCY0i74WpJumMQe.jpg"
            }
        ],
        "crew": [
            {
                "name": "Ridley Scott",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/zABJmN9opmqD4orWl3KSdCaSo7Q.jpg"
            },
            {
                "name": "Hans Zimmer",
                "role": "Original Music Composer",
                "photo_url": "https://image.tmdb.org/t/p/w300/tpQnDeHY15szIXvpnhlprufz4d.jpg"
            }
        ]
    },
    "the final whistle": {
        "cast": [
            {
                "name": "Christian Bale",
                "role": "Coach Marcus",
                "photo_url": "https://image.tmdb.org/t/p/w300/7Pxez9J8fuPd2Mn9kex13YALrCQ.jpg"
            },
            {
                "name": "Florence Pugh",
                "role": "Dr. Clara Evans",
                "photo_url": "https://image.tmdb.org/t/p/w300/2URrZb95t3kY6pLroKny3Enmabp.jpg"
            },
            {
                "name": "John Boyega",
                "role": "Leo Stone",
                "photo_url": "https://image.tmdb.org/t/p/w300/3153CfpgZQXTzCY0i74WpJumMQe.jpg"
            },
            {
                "name": "Woody Harrelson",
                "role": "General Vance",
                "photo_url": "https://image.tmdb.org/t/p/w300/igxYDQBbTEdAqaJxaW6ffqswmUU.jpg"
            }
        ],
        "crew": [
            {
                "name": "Ridley Scott",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/zABJmN9opmqD4orWl3KSdCaSo7Q.jpg"
            },
            {
                "name": "Hans Zimmer",
                "role": "Original Music Composer",
                "photo_url": "https://image.tmdb.org/t/p/w300/tpQnDeHY15szIXvpnhlprufz4d.jpg"
            }
        ]
    },
    "amaran": {
        "cast": [
            {
                "name": "Sivakarthikeyan",
                "role": "Major Mukund Varadarajan",
                "photo_url": "https://image.tmdb.org/t/p/w300/jgy9y3V8QqZmu5r8sMxrGCzXuyp.jpg"
            },
            {
                "name": "Sai Pallavi",
                "role": "Indhu Rebecca Varghese",
                "photo_url": "https://image.tmdb.org/t/p/w300/qAPdGKUIUEzLibdgVCey7oKvvME.jpg"
            },
            {
                "name": "Rahul Bose",
                "role": "Colonel Amit Singh Dabas",
                "photo_url": "https://image.tmdb.org/t/p/w300/6T0xhsganOB8SI48HCGd99XKj9l.jpg"
            },
            {
                "name": "Bhuvan Arora",
                "role": "Vikram Singh",
                "photo_url": "https://image.tmdb.org/t/p/w300/AtEfX9ta8LZTWh7yZ4dVc2wpIRO.jpg"
            },
            {
                "name": "Lallu Prasath",
                "role": "Ravi Shankar",
                "photo_url": "https://image.tmdb.org/t/p/w300/f6TVtddrbG1Qk1brFASrpPehpQh.jpg"
            },
            {
                "name": "Anbu Thasan",
                "role": "Sepoy",
                "photo_url": "https://image.tmdb.org/t/p/w300/ycX5zV4CVOoSMnM3wkoOndZHaP7.jpg"
            },
            {
                "name": "Shreekumar",
                "role": "Michael",
                "photo_url": "https://image.tmdb.org/t/p/w300/rgpQi9g4h4EzQQv7fXKhnEGWLq5.jpg"
            },
            {
                "name": "Shyamaprasad",
                "role": "R. Varadarajan",
                "photo_url": "https://image.tmdb.org/t/p/w300/7XmS8tF5OGt7y9YdpyySIWBECkH.jpg"
            },
            {
                "name": "Shyam Mohan",
                "role": "Indhu's brother",
                "photo_url": "https://image.tmdb.org/t/p/w300/wqUndf8mfVUxKtus68hrh7dlBhX.jpg"
            },
            {
                "name": "Paul T Baby",
                "role": "Andrews",
                "photo_url": None
            }
        ],
        "crew": [
            {
                "name": "C. H. Sai",
                "role": "Director of Photography",
                "photo_url": None
            },
            {
                "name": "R. Kalaivanan",
                "role": "Editor",
                "photo_url": None
            },
            {
                "name": "Rajkumar Periasamy",
                "role": "Director",
                "photo_url": None
            },
            {
                "name": "Kamal Haasan",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/17zscZgz4wOlGDd3Gziw4YbI3G.jpg"
            },
            {
                "name": "R. Mahendran",
                "role": "Producer",
                "photo_url": None
            },
            {
                "name": "G. V. Prakash Kumar",
                "role": "Original Music Composer",
                "photo_url": "https://image.tmdb.org/t/p/w300/ArX3l6CdNo0sGI8b6PFYveR9Azm.jpg"
            },
            {
                "name": "Vivek Krishnani",
                "role": "Producer",
                "photo_url": None
            }
        ]
    },
    "manjummel boys": {
        "cast": [
            {
                "name": "Soubin Shahir",
                "role": "Siju 'Kuttan' David",
                "photo_url": "https://image.tmdb.org/t/p/w300/eFMA1PFOpDtiJ5MlkSAMexvTPsl.jpg"
            },
            {
                "name": "Sreenath Bhasi",
                "role": "Subash",
                "photo_url": "https://image.tmdb.org/t/p/w300/oPsXUtaE0ZslhaGRdtww0ZpMRe7.jpg"
            },
            {
                "name": "Balu Varghese",
                "role": "Sixen John",
                "photo_url": "https://image.tmdb.org/t/p/w300/v1Ydyfxe3bFxXiHB4cU5Hmoh5hV.jpg"
            },
            {
                "name": "Ganapathi S. Poduval",
                "role": "Krishnakumar 'Kannan'",
                "photo_url": "https://image.tmdb.org/t/p/w300/15g6TQroqoLmcK1E8CniGZjm72l.jpg"
            },
            {
                "name": "Lal Jr.",
                "role": "Siju John",
                "photo_url": "https://image.tmdb.org/t/p/w300/2QoAFcXlCwZNlYy6gTr3S2GY39o.jpg"
            },
            {
                "name": "Deepak Parambol",
                "role": "Sudheesh",
                "photo_url": "https://image.tmdb.org/t/p/w300/unP6XX7SDtatBVuVG8CVhwQTAQ5.jpg"
            },
            {
                "name": "Abhiram Radhakrishnan",
                "role": "Anil",
                "photo_url": "https://image.tmdb.org/t/p/w300/8AjTvCsrPkiOLYblggiMlUAketU.jpg"
            },
            {
                "name": "Arun Kurian",
                "role": "Sujith",
                "photo_url": "https://image.tmdb.org/t/p/w300/7jFTigCmJV3xH0fKSkv1wbdbdKo.jpg"
            },
            {
                "name": "Chandu Salimkumar",
                "role": "Abhilash",
                "photo_url": "https://image.tmdb.org/t/p/w300/1FVTLZWJi7acmNYQYdnkWsld9nr.jpg"
            },
            {
                "name": "Vishnu Reghu",
                "role": "Jinsen",
                "photo_url": "https://image.tmdb.org/t/p/w300/gGnA8Fxi4QYyxobWxLCtKDVF9nL.jpg"
            }
        ],
        "crew": [
            {
                "name": "Shyju Khalid",
                "role": "Director of Photography",
                "photo_url": "https://image.tmdb.org/t/p/w300/pp5QwB4fx0zONvNT6WlTm2pb7tq.jpg"
            },
            {
                "name": "Chidambaram",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/fwRYox7fTSVurHJJnsAQCUJ7Jzt.jpg"
            },
            {
                "name": "Soubin Shahir",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/eFMA1PFOpDtiJ5MlkSAMexvTPsl.jpg"
            },
            {
                "name": "Sushin Shyam",
                "role": "Original Music Composer",
                "photo_url": "https://image.tmdb.org/t/p/w300/d9gCNGQGmQIfbPl8cDcbVe13AsN.jpg"
            },
            {
                "name": "Vivek Harshan",
                "role": "Editor",
                "photo_url": "https://image.tmdb.org/t/p/w300/zWZoAzJHfovG4ox16QiUVZLN9HA.jpg"
            },
            {
                "name": "Babu Shahir",
                "role": "Producer",
                "photo_url": None
            },
            {
                "name": "Shawn Antony",
                "role": "Producer",
                "photo_url": None
            }
        ]
    },
    "aavesham": {
        "cast": [
            {
                "name": "Fahadh Faasil",
                "role": "Ranjith 'Ranga' Gangadharan",
                "photo_url": "https://image.tmdb.org/t/p/w300/wmkwZWFHqMptqdt4HacMIAe8OBP.jpg"
            },
            {
                "name": "Hipster",
                "role": "Aju",
                "photo_url": "https://image.tmdb.org/t/p/w300/zUKB1gDZiCLB3u1zEnp8W7UtYCU.jpg"
            },
            {
                "name": "Mithun Jai Sankar",
                "role": "Bibi",
                "photo_url": "https://image.tmdb.org/t/p/w300/r3ynMua2UoFlLnEP8PEEe3x2PnT.jpg"
            },
            {
                "name": "Roshan Shanavas",
                "role": "Shanthan",
                "photo_url": "https://image.tmdb.org/t/p/w300/lotiqK0sfK4rZKV6tHvHrg9Cty3.jpg"
            },
            {
                "name": "Sajin Gopu",
                "role": "Amban",
                "photo_url": "https://image.tmdb.org/t/p/w300/l8kpWfPvD7Gzp2LgvRSWVRsrxWd.jpg"
            },
            {
                "name": "Midhun Midhutty",
                "role": "Kuttettan",
                "photo_url": None
            },
            {
                "name": "Krishna Kumar",
                "role": "Nanjappa",
                "photo_url": None
            },
            {
                "name": "Freestyle Krishna",
                "role": "Bruce-Lee",
                "photo_url": None
            },
            {
                "name": "Himanshu",
                "role": "Jacky",
                "photo_url": None
            },
            {
                "name": "Mansoor Ali Khan",
                "role": "Reddy",
                "photo_url": "https://image.tmdb.org/t/p/w300/bXNi9n6Y4dz85xdLnjxquKHleuZ.jpg"
            }
        ],
        "crew": [
            {
                "name": "Sameer Thahir",
                "role": "Director of Photography",
                "photo_url": "https://image.tmdb.org/t/p/w300/m7Cr6VhwS5wYRWxBpGkX4oUwxFw.jpg"
            },
            {
                "name": "Jithu Madhavan",
                "role": "Writer",
                "photo_url": "https://image.tmdb.org/t/p/w300/hw3v8VDPlMBdVDweSKH5IcLgdGP.jpg"
            },
            {
                "name": "Anwar Rasheed",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/670MKLVvf3zQCQ2474T3mGigiBU.jpg"
            },
            {
                "name": "Sushin Shyam",
                "role": "Original Music Composer",
                "photo_url": "https://image.tmdb.org/t/p/w300/d9gCNGQGmQIfbPl8cDcbVe13AsN.jpg"
            },
            {
                "name": "Vivek Harshan",
                "role": "Editor",
                "photo_url": "https://image.tmdb.org/t/p/w300/zWZoAzJHfovG4ox16QiUVZLN9HA.jpg"
            },
            {
                "name": "Nazriya Nazim",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/eXTaWA5jp7kW7gupWt6bGCKE4DI.jpg"
            },
            {
                "name": "Fahadh Faasil",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/wmkwZWFHqMptqdt4HacMIAe8OBP.jpg"
            }
        ]
    },
    "i am game": {
        "cast": [
            {
                "name": "Prithviraj Sukumaran",
                "role": "David Koshy",
                "photo_url": "https://image.tmdb.org/t/p/w300/1xhG42QU8tMQRTDdP1Ed3y9GRvm.jpg"
            },
            {
                "name": "Nayanthara",
                "role": "Ananya",
                "photo_url": "https://image.tmdb.org/t/p/w300/sYUzvjsSsqeOgBblSzda6ZwwbEa.jpg"
            },
            {
                "name": "Tovino Thomas",
                "role": "Neil",
                "photo_url": "https://image.tmdb.org/t/p/w300/uySCXY4TZxEDcVJD8WOjDQmMHc9.jpg"
            },
            {
                "name": "Indrajith Sukumaran",
                "role": "Roy",
                "photo_url": "https://image.tmdb.org/t/p/w300/32YxjXVmgkPCVKUQAkNqWUGbBIl.jpg"
            },
            {
                "name": "Suraj Venjaramoodu",
                "role": "Mathew",
                "photo_url": "https://image.tmdb.org/t/p/w300/2FUs0wmR3eHBd8g4GVbCmhkUzeI.jpg"
            }
        ],
        "crew": [
            {
                "name": "Jeethu Joseph",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/47Hqs5fHKFU0uRb0qIJOncAcqNl.jpg"
            },
            {
                "name": "Antony Perumbavoor",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/3jyOxhNgNljnuGJeEx9Yth9zjoP.jpg"
            },
            {
                "name": "Jakes Bejoy",
                "role": "Original Music Composer",
                "photo_url": "https://image.tmdb.org/t/p/w300/n1JPfYACCoK6wzXUGITLvw3ku7F.jpg"
            }
        ]
    },
    "vaazha": {
        "cast": [
            {
                "name": "Siju Sunny",
                "role": "Ajo Thomas",
                "photo_url": "https://image.tmdb.org/t/p/w300/85mAvBMgIVo0C8kkeuEgsbLfifZ.jpg"
            },
            {
                "name": "Joemon Jyothir",
                "role": "Moosa",
                "photo_url": "https://image.tmdb.org/t/p/w300/prwllSgqHxG5c8yQGtXGnH5LbPh.jpg"
            },
            {
                "name": "Safwan",
                "role": "Vishwam",
                "photo_url": None
            },
            {
                "name": "Amith Mohan Rajeswari",
                "role": "Vishnu Radhakrishnan",
                "photo_url": "https://image.tmdb.org/t/p/w300/x64tksObwq5TlKZ2pZmDawMwAq4.jpg"
            },
            {
                "name": "Ajin Joy",
                "role": "Ajin",
                "photo_url": "https://image.tmdb.org/t/p/w300/flaXVOZYukvtbzmQb4S8qPZSwvX.jpg"
            },
            {
                "name": "Azees Nedumangad",
                "role": "Thomachan",
                "photo_url": "https://image.tmdb.org/t/p/w300/zsPdTjTxeFtwjqG7tIJrFcF45V5.jpg"
            },
            {
                "name": "Kottayam Nazeer",
                "role": "Radhakrishnan",
                "photo_url": "https://image.tmdb.org/t/p/w300/vN0cHxgDIE5DKUeL2F0nmIhTIoZ.jpg"
            },
            {
                "name": "Noby Marcose",
                "role": "Ibrahim",
                "photo_url": "https://image.tmdb.org/t/p/w300/o2E8IhRc7T3kyZeebXC5nX3Bepz.jpg"
            },
            {
                "name": "Meenakshi Unnikrishnan",
                "role": "Maya",
                "photo_url": "https://image.tmdb.org/t/p/w300/vEBiMtuPMRz6MvaB1q8Pjs4tajy.jpg"
            },
            {
                "name": "Anuraj OB",
                "role": "Abdul Kalam",
                "photo_url": "https://image.tmdb.org/t/p/w300/3sOaLataDZ8o9mIGTcv7HxaawLt.jpg"
            }
        ],
        "crew": [
            {
                "name": "Harris Desom",
                "role": "Producer",
                "photo_url": None
            },
            {
                "name": "Vipin Das",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/nSvwYnZT6DgSJMJBR9qgF3AP4kg.jpg"
            },
            {
                "name": "Anand Menen",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/m2LryP6KuvYziyORvmIS8DCKUzk.jpg"
            },
            {
                "name": "Aravind Puthussery",
                "role": "Director of Photography",
                "photo_url": None
            },
            {
                "name": "Adarsh Narayan",
                "role": "Producer",
                "photo_url": None
            },
            {
                "name": "Kannan Mohan",
                "role": "Editor",
                "photo_url": None
            },
            {
                "name": "Electronic Kili",
                "role": "Music",
                "photo_url": "https://image.tmdb.org/t/p/w300/6QtRyFXDdnkr1dUhQidtqHIZLps.jpg"
            },
            {
                "name": "Rajat Prakash",
                "role": "Music",
                "photo_url": None
            }
        ]
    },
    "deadpool & wolverine": {
        "cast": [
            {
                "name": "Ryan Reynolds",
                "role": "Wade Wilson / Deadpool / Nicepool",
                "photo_url": "https://image.tmdb.org/t/p/w300/trzgptffGvAlAT6MEu01fz47cLW.jpg"
            },
            {
                "name": "Hugh Jackman",
                "role": "Logan / Wolverine",
                "photo_url": "https://image.tmdb.org/t/p/w300/4Xujtewxqt6aU0Y81tsS9gkjizk.jpg"
            },
            {
                "name": "Emma Corrin",
                "role": "Cassandra Nova",
                "photo_url": "https://image.tmdb.org/t/p/w300/hp5KW9RpavorNnsQxybB0qBEnyd.jpg"
            },
            {
                "name": "Matthew Macfadyen",
                "role": "Mr. Paradox",
                "photo_url": "https://image.tmdb.org/t/p/w300/sFaIfkykJdftwrc3BdEfpdg2mYW.jpg"
            },
            {
                "name": "Dafne Keen",
                "role": "Laura / X-23",
                "photo_url": "https://image.tmdb.org/t/p/w300/34BhddK5z2YHjfppOleezVrQ7Jt.jpg"
            },
            {
                "name": "Jon Favreau",
                "role": "Happy Hogan",
                "photo_url": "https://image.tmdb.org/t/p/w300/tnx7iMVydPQXGOoLsxXl84PXtbA.jpg"
            },
            {
                "name": "Morena Baccarin",
                "role": "Vanessa",
                "photo_url": "https://image.tmdb.org/t/p/w300/4gyHyg6FJ1oFczOm5pmMkdEEo2J.jpg"
            },
            {
                "name": "Rob Delaney",
                "role": "Peter",
                "photo_url": "https://image.tmdb.org/t/p/w300/xirfT1znRkkughLiPemKu3NhkKQ.jpg"
            },
            {
                "name": "Leslie Uggams",
                "role": "Blind Al",
                "photo_url": "https://image.tmdb.org/t/p/w300/8zQO5GNWQwJG4we5AYfjopblRFe.jpg"
            },
            {
                "name": "Jennifer Garner",
                "role": "Elektra",
                "photo_url": "https://image.tmdb.org/t/p/w300/eiX083VOa0RCGSgwENZgVi5MgDi.jpg"
            }
        ],
        "crew": [
            {
                "name": "Shawn Levy",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/rpAvyeds9OztUQUUMmgg7eivfLY.jpg"
            },
            {
                "name": "Rhett Reese",
                "role": "Writer",
                "photo_url": "https://image.tmdb.org/t/p/w300/qmllR1OPT0wG0gGBrGF0bvgY2wZ.jpg"
            },
            {
                "name": "Paul Wernick",
                "role": "Writer",
                "photo_url": "https://image.tmdb.org/t/p/w300/eEJBp1R3kmVKYq8IT0xUGUMUKim.jpg"
            },
            {
                "name": "Shane Reid",
                "role": "Editor",
                "photo_url": "https://image.tmdb.org/t/p/w300/idptgX7GBTwqcM7WKKaChThDFQN.jpg"
            },
            {
                "name": "Ryan Reynolds",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/trzgptffGvAlAT6MEu01fz47cLW.jpg"
            },
            {
                "name": "Lauren Shuler Donner",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/a0oY5BiS6ubJv3Mxh83XH8S4fH7.jpg"
            },
            {
                "name": "Dean Zimmerman",
                "role": "Editor",
                "photo_url": "https://image.tmdb.org/t/p/w300/adIjjwmv9b4Rbufz9ggC54f56vc.jpg"
            },
            {
                "name": "Zeb Wells",
                "role": "Writer",
                "photo_url": "https://image.tmdb.org/t/p/w300/cfc4Y9MjnAMSr0Fs68M4nubvSIQ.jpg"
            }
        ]
    },
    "avengers: endgame encore": {
        "cast": [
            {
                "name": "Robert Downey Jr.",
                "role": "Tony Stark / Iron Man",
                "photo_url": "https://image.tmdb.org/t/p/w300/5qHNjhtjMD4YWH3UP0rm4tKwxCL.jpg"
            },
            {
                "name": "Chris Evans",
                "role": "Steve Rogers / Captain America",
                "photo_url": "https://image.tmdb.org/t/p/w300/3bOGNsHlrswhyW79uvIHH1V43JI.jpg"
            },
            {
                "name": "Mark Ruffalo",
                "role": "Bruce Banner / Hulk",
                "photo_url": "https://image.tmdb.org/t/p/w300/5GilHMOt5PAQh6rlUKZzGmaKEI7.jpg"
            },
            {
                "name": "Chris Hemsworth",
                "role": "Thor",
                "photo_url": "https://image.tmdb.org/t/p/w300/piQGdoIQOF3C1EI5cbYZLAW1gfj.jpg"
            },
            {
                "name": "Scarlett Johansson",
                "role": "Natasha Romanoff / Black Widow",
                "photo_url": "https://image.tmdb.org/t/p/w300/tgxYh3jMs5bY2Ub4d2dcp9iaz1R.jpg"
            },
            {
                "name": "Jeremy Renner",
                "role": "Clint Barton / Hawkeye",
                "photo_url": "https://image.tmdb.org/t/p/w300/yB84D1neTYXfWBaV0QOE9RF2VCu.jpg"
            },
            {
                "name": "Josh Brolin",
                "role": "Thanos",
                "photo_url": "https://image.tmdb.org/t/p/w300/sX2etBbIkxRaCsATyw5ZpOVMPTD.jpg"
            },
            {
                "name": "Don Cheadle",
                "role": "James Rhodes / War Machine",
                "photo_url": "https://image.tmdb.org/t/p/w300/umhTmcVF26qZKEpSfG1ZNpcbs9D.jpg"
            },
            {
                "name": "Paul Rudd",
                "role": "Scott Lang / Ant-Man",
                "photo_url": "https://image.tmdb.org/t/p/w300/6jtwNOLKy0LdsRAKwZqgYMAfd5n.jpg"
            },
            {
                "name": "Benedict Cumberbatch",
                "role": "Doctor Strange",
                "photo_url": "https://image.tmdb.org/t/p/w300/wz3MRiMmoz6b5X3oSzMRC9nLxY1.jpg"
            }
        ],
        "crew": [
            {
                "name": "Kevin Feige",
                "role": "Producer",
                "photo_url": "https://image.tmdb.org/t/p/w300/kCBqXZ5PT5udYGEj2wfTSFbLMvT.jpg"
            },
            {
                "name": "Alan Silvestri",
                "role": "Original Music Composer",
                "photo_url": "https://image.tmdb.org/t/p/w300/feUZ0Oc1MGJJbUronBbkHTmJzgy.jpg"
            },
            {
                "name": "Christopher Markus",
                "role": "Screenplay",
                "photo_url": "https://image.tmdb.org/t/p/w300/7ooPNp0gnURxYkSSKF2etH7wpZP.jpg"
            },
            {
                "name": "Stephen McFeely",
                "role": "Screenplay",
                "photo_url": "https://image.tmdb.org/t/p/w300/i9B6gFzExPsh5IEjD2nn4ym4lx2.jpg"
            },
            {
                "name": "Jeffrey Ford",
                "role": "Editor",
                "photo_url": "https://image.tmdb.org/t/p/w300/fJePTuHsOeT8z4D6LFZlSMkDEqF.jpg"
            },
            {
                "name": "Matthew Schmidt",
                "role": "Editor",
                "photo_url": None
            },
            {
                "name": "Trent Opaloch",
                "role": "Director of Photography",
                "photo_url": "https://image.tmdb.org/t/p/w300/w8xfY8rGXdCx2zna0nLeVpx91lx.jpg"
            },
            {
                "name": "Anthony Russo",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/xbINBnWn28YygYWUJ1aSAw0xPRv.jpg"
            }
        ]
    },
    "marco": {
        "cast": [
            {
                "name": "Unni Mukundan",
                "role": "Marco Jr.",
                "photo_url": "https://image.tmdb.org/t/p/w300/7Pn9GASysyTG6ZnPhsuRq4ESArC.jpg"
            },
            {
                "name": "Siddique",
                "role": "George D'Peter",
                "photo_url": "https://image.tmdb.org/t/p/w300/tMv7QsmYlXAXtP75D3eIxXHpgTv.jpg"
            },
            {
                "name": "Ishan Shoukath",
                "role": "Victor D'Peter",
                "photo_url": "https://image.tmdb.org/t/p/w300/xJicLr2st7kQT7fzPC2xAZnzGUx.jpg"
            },
            {
                "name": "Jagadish",
                "role": "Tony Issac",
                "photo_url": "https://image.tmdb.org/t/p/w300/ml3XX5bWPIdHUPvqhW2MYYZ8H7Y.jpg"
            },
            {
                "name": "Abhimanyu Thilakan",
                "role": "Russell Issac",
                "photo_url": "https://image.tmdb.org/t/p/w300/6X1X5aJi9JkF9nhNuy1bEY8RD05.jpg"
            },
            {
                "name": "Kabir Duhan Singh",
                "role": "Cyrus Issac",
                "photo_url": "https://image.tmdb.org/t/p/w300/lAVAxFARP63oTHMYWpwHrWsXPWa.jpg"
            },
            {
                "name": "Anson Paul",
                "role": "Dev",
                "photo_url": "https://image.tmdb.org/t/p/w300/tuuQTQFh4qMY7EOP9rgVlz0Y57y.jpg"
            },
            {
                "name": "Ajit Koshy",
                "role": "Jahangir",
                "photo_url": "https://image.tmdb.org/t/p/w300/qR765VN5mOHfosx23NBMTxWuw6h.jpg"
            },
            {
                "name": "Durva Thaker",
                "role": "Isha",
                "photo_url": None
            },
            {
                "name": "Yukti Thareja",
                "role": "Mariya",
                "photo_url": "https://image.tmdb.org/t/p/w300/aUcMSWJMz5ur0AagUYC8jQBsV32.jpg"
            }
        ],
        "crew": [
            {
                "name": "Haneef Adeni",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/jsuiJYAvw5pGnkK9hMNg0ddtPm7.jpg"
            },
            {
                "name": "Abdul Ghadaf",
                "role": "Producer",
                "photo_url": None
            },
            {
                "name": "Shareef Muhammed",
                "role": "Producer",
                "photo_url": None
            },
            {
                "name": "Ravi Basrur",
                "role": "Original Music Composer",
                "photo_url": "https://image.tmdb.org/t/p/w300/mlHRC8r4J3ZND7w80B59x3WeX1I.jpg"
            },
            {
                "name": "Shameer Muhammed",
                "role": "Editor",
                "photo_url": "https://image.tmdb.org/t/p/w300/7dN5MFUDP0tiZXXLkTlJw5gutGD.jpg"
            },
            {
                "name": "Chandru Selvaraj",
                "role": "Director of Photography",
                "photo_url": None
            }
        ]
    },
    "bramayugam": {
        "cast": [
            {
                "name": "Arjun Ashokan",
                "role": "Thevan",
                "photo_url": "https://image.tmdb.org/t/p/w300/fA9V9ImvGlLGQ9HWB68j8d8eo0J.jpg"
            },
            {
                "name": "Mammootty",
                "role": "Kodumon Potti",
                "photo_url": "https://image.tmdb.org/t/p/w300/c5ewp9XtDIOwK5QWhwA7TD0GzqO.jpg"
            },
            {
                "name": "Sidharth Bharathan",
                "role": "Servant",
                "photo_url": "https://image.tmdb.org/t/p/w300/4a13KELmZuB4NnRlOsdzMfo2K7j.jpg"
            },
            {
                "name": "Manikandan Achari",
                "role": "Koran",
                "photo_url": "https://image.tmdb.org/t/p/w300/5yLbdEwBpSAUajsvLM9eY1fsymp.jpg"
            },
            {
                "name": "Amalda Liz",
                "role": "Yakshi",
                "photo_url": "https://image.tmdb.org/t/p/w300/4FcPoRJtqMLVZ0E5cadiq4Hdr0J.jpg"
            },
            {
                "name": "Aluva Sheeba Sebastian",
                "role": "Thevan's Mother",
                "photo_url": None
            },
            {
                "name": "Akash Chandran",
                "role": "Goblin",
                "photo_url": None
            },
            {
                "name": "Rafnas Rafeek",
                "role": "Theyyam",
                "photo_url": None
            },
            {
                "name": "Sergi",
                "role": "Portuguese Infantryman 2",
                "photo_url": None
            },
            {
                "name": "Andr\u00e8",
                "role": "Portuguese Infantryman 1",
                "photo_url": None
            }
        ],
        "crew": [
            {
                "name": "Rahul Sadasivan",
                "role": "Director",
                "photo_url": "https://image.tmdb.org/t/p/w300/m61dA8W9fLdhgfLMdEPXalPYush.jpg"
            },
            {
                "name": "Chakravarthy Ramachandra",
                "role": "Producer",
                "photo_url": None
            },
            {
                "name": "S. Sashikanth",
                "role": "Producer",
                "photo_url": None
            },
            {
                "name": "Shehnad Jalal",
                "role": "Director of Photography",
                "photo_url": "https://image.tmdb.org/t/p/w300/q589cqyiscSQ9sKD0bYJFlgzxfe.jpg"
            },
            {
                "name": "Christo Xavier",
                "role": "Original Music Composer",
                "photo_url": None
            },
            {
                "name": "Shafique Mohamed Ali",
                "role": "Editor",
                "photo_url": None
            }
        ]
    }
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


async def _fetch_showtimes(client: httpx.AsyncClient, base_url: str, max_retries: int = 5) -> list[dict]:
    url = f"{base_url.rstrip('/')}/v1/showtimes"
    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.get(url, timeout=40.0)
            if resp.status_code in (502, 503, 504) and attempt < max_retries:
                wait_s = 5 * attempt
                print(
                    f"     [spin-up retry {attempt}/{max_retries}] HTTP {resp.status_code} from {base_url}, "
                    f"waiting {wait_s}s for instance to wake up..."
                )
                await asyncio.sleep(wait_s)
                continue
            resp.raise_for_status()
            return resp.json()
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as err:
            if attempt < max_retries:
                wait_s = 5 * attempt
                print(
                    f"     [spin-up retry {attempt}/{max_retries}] {type(err).__name__} from {base_url}, "
                    f"waiting {wait_s}s for instance to wake up..."
                )
                await asyncio.sleep(wait_s)
                continue
            raise
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
        poster_url = st.get("poster_url") or DEFAULT_POSTER
        banner_url = st.get("banner_url")   

        movie = movies_by_title.get(title)
        if not movie:
            release_year = st.get("release_year")
            release_date = (
                datetime(release_year, 1, 1, tzinfo=timezone.utc)
                if release_year else None
            )
            movie = Movie(
                id=uuid.uuid4(),
                title=title,
                language=st.get("language", "Malayalam"),
                duration_min=st.get("duration_min", 150),
                certificate=st.get("certificate", "UA"),
                status="PUBLISHED",
                partner_id=partner_id,
                poster_url=poster_url,
                banner_url=banner_url,
                release_date=release_date,
                genre=st.get("genre"),
                synopsis=f"Now showing: {title}",
                cast_json=st.get("cast") or [],
                crew_json=st.get("crew") or [],
            )
            new_movies.append(movie)
            movies_by_title[title] = movie
        else:
            movie.poster_url = poster_url
            movie.genre = st.get("genre")
            release_year = st.get("release_year")
            if release_year:
                movie.release_date = datetime(release_year, 1, 1, tzinfo=timezone.utc)
            # Only overwrite cast/crew if the provider actually sends them
            if st.get("cast"):
                movie.cast_json = st["cast"]
            if st.get("crew"):
                movie.crew_json = st["crew"]

        cinema_name = st.get("cinema_name") or "Unknown Cinema"
        city = st.get("city") or "Kochi"
        screen_name = st.get("screen_name") or "Screen 1"
        screen = screens_by_key[(cinema_name, city, screen_name)]
        starts_at_dt = datetime.fromisoformat(st["starts_at"].replace("Z", "+00:00"))

        existing_st = showtimes_by_ref.get(st["id"])
        if not existing_st:
            new_showtimes.append(Showtime(
                id=uuid.uuid4(),
                screen_id=screen.id,
                movie_id=movie.id,
                starts_at=starts_at_dt,
                language=st.get("language", "Malayalam"),
                format="2D",
                status="ACTIVE",
                partner_id=partner_id,
                provider_id=provider.id,
                provider_showtime_ref=st["id"],
            ))
        else:
            existing_st.screen_id = screen.id
            existing_st.starts_at = starts_at_dt
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