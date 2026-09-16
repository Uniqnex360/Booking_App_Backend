import asyncio
import os
import sys
import uuid
import httpx
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.database import AsyncSessionLocal
import app.auth.models
import app.partner.models
import app.event.models
import app.movie.models
from app.auth.models import User
from app.partner.models import PartnerORM
from app.movie.models import Venue, Screen, Movie, Showtime
from app.shared.providers.registry import ProviderRegistryModel
from sqlalchemy import select, update

PVR_URL = os.getenv("PVR_BASE_URL", "https://pvr-backend-pejx.onrender.com").rstrip("/")
PVR_EMAIL = os.getenv("PVR_ADMIN_EMAIL", "demo@pvr.local")
PVR_PASSWORD = os.getenv("PVR_ADMIN_PASSWORD", "demo1234")

POSTER_MAP = {
    "i am game": "https://m.media-amazon.com/images/M/MV5BZTU1YjI3MjAtYzU4OC00MzZkLWIwMTctZTA0NzA2MmQ4M2U3XkEyXkFqcGc@._V1_FMjpg_UX1000_.jpg",
    "the final whistle": "https://images.unsplash.com/photo-1508098682722-e99c43a406b2?w=800&auto=format&fit=crop&q=80",
}

async def sync_production():
    print(f"1. Connecting to PVR at: {PVR_URL}")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            login_resp = await client.post(
                f"{PVR_URL}/v1/auth/login",
                json={"email": PVR_EMAIL, "password": PVR_PASSWORD},
            )
            pvr_token = login_resp.json().get("token") if login_resp.status_code == 200 else None

            st_resp = await client.get(f"{PVR_URL}/v1/showtimes")
            pvr_showtimes = st_resp.json()
        except Exception as e:
            print(f"Error connecting to PVR ({PVR_URL}): {e}")
            return

    if not pvr_showtimes:
        print("No showtimes returned from PVR.")
        return

    async with AsyncSessionLocal() as session:
        partner_query = await session.execute(
            select(PartnerORM).where(PartnerORM.business_name == "PVR Cinemas Ltd")
        )
        partner_orm = partner_query.scalar_one_or_none()

        if not partner_orm:
            partner_user_id = uuid.uuid4()
            partner_id = uuid.uuid4()
            partner_user = User(
                id=partner_user_id,
                full_name="PVR Cinemas Partner",
                email="partner_pvr@vignette.local",
                password_hash="system_managed",
                role="PARTNER",
                is_active=True,
            )
            session.add(partner_user)
            await session.flush()

            partner_orm = PartnerORM(
                id=partner_id,
                user_id=partner_user_id,
                business_name="PVR Cinemas Ltd",
                partner_type="event_organiser",
                contact_name="PVR Manager",
                contact_phone="9876543210",
                city="Kochi",
                status="APPROVED",
            )
            session.add(partner_orm)
            await session.flush()
        else:
            partner_id = partner_orm.id

        venue_query = await session.execute(select(Venue).where(Venue.name == "PVR Lulu Mall"))
        venue = venue_query.scalar_one_or_none()
        if not venue:
            venue = Venue(
                id=uuid.uuid4(),
                name="PVR Lulu Mall",
                city="Kochi",
                address="Lulu Mall, Edappally, Kochi",
                timezone="Asia/Kolkata",
                partner_id=partner_id,
            )
            session.add(venue)
            await session.flush()

        screen_query = await session.execute(select(Screen).where(Screen.venue_id == venue.id))
        screen = screen_query.scalar_one_or_none()
        if not screen:
            screen = Screen(
                id=uuid.uuid4(),
                venue_id=venue.id,
                name="Audi 1 (IMAX)",
                total_seats=234,
            )
            session.add(screen)
            await session.flush()

        provider_query = await session.execute(
            select(ProviderRegistryModel).where(ProviderRegistryModel.name.ilike("%pvr%"))
        )
        provider = provider_query.scalar_one_or_none()
        if not provider:
            provider = ProviderRegistryModel(
                id=uuid.uuid4(),
                name="PVR Provider",
                base_url=PVR_URL,
                auth_token_ref=pvr_token,
                hold_ttl_seconds=600,
                enabled=True,
                partner_id=partner_id,
            )
            session.add(provider)
            await session.flush()
        else:
            provider.base_url = PVR_URL
            if pvr_token:
                provider.auth_token_ref = pvr_token
            await session.flush()

        current_pvr_ids = [st["id"] for st in pvr_showtimes]
        await session.execute(
            update(Showtime)
            .where(
                Showtime.provider_id == provider.id,
                Showtime.provider_showtime_ref.notin_(current_pvr_ids),
            )
            .values(status="CANCELLED")
        )

        synced = 0
        for st in pvr_showtimes:
            title = st["movie_title"]
            title_clean = title.lower().strip()
            poster_url = POSTER_MAP.get(
                title_clean,
                "https://images.unsplash.com/photo-1489599849927-2ee91cede3ba?w=800&auto=format&fit=crop&q=80",
            )

            movie_q = await session.execute(select(Movie).where(Movie.title == title))
            movie = movie_q.scalar_one_or_none()
            if not movie:
                movie = Movie(
                    id=uuid.uuid4(),
                    title=title,
                    language=st.get("language", "Malayalam"),
                    duration_min=st.get("duration_min", 150),
                    certificate=st.get("certificate", "UA"),
                    status="PUBLISHED",
                    partner_id=partner_id,
                    poster_url=poster_url,
                    synopsis=f"Now showing at PVR Cinemas: {title}",
                )
                session.add(movie)
                await session.flush()
            else:
                movie.poster_url = poster_url
                await session.flush()

            starts_at_dt = datetime.fromisoformat(st["starts_at"].replace("Z", "+00:00"))

            existing_st = (await session.execute(
                select(Showtime).where(Showtime.provider_showtime_ref == st["id"])
            )).scalar_one_or_none()

            if not existing_st:
                new_st = Showtime(
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
                )
                session.add(new_st)
                synced += 1
            else:
                existing_st.starts_at = starts_at_dt
                existing_st.provider_id = provider.id
                existing_st.status = "ACTIVE"
                synced += 1

        await session.commit()
        print(f"Synced {synced} showtime(s) with custom posters.")

if __name__ == "__main__":
    asyncio.run(sync_production())
