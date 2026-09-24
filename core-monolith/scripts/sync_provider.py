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
            )
            new_movies.append(movie)
            movies_by_title[title] = movie
        else:
            movie.poster_url = poster_url
            movie.genre = st.get("genre")
            release_year = st.get("release_year")
            if release_year:
                movie.release_date = datetime(release_year, 1, 1, tzinfo=timezone.utc)

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