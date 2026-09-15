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
from sqlalchemy import select, delete

PVR_URL = os.getenv("PVR_BASE_URL", "https://pvr-backend-pejx.onrender.com").rstrip("/")
PVR_EMAIL = os.getenv("PVR_ADMIN_EMAIL", "demo@pvr.local")
PVR_PASSWORD = os.getenv("PVR_ADMIN_PASSWORD", "demo1234")

async def sync_production():
    print(f"1. Connecting to PVR at: {PVR_URL}")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Login to PVR
            login_resp = await client.post(
                f"{PVR_URL}/v1/auth/login",
                json={"email": PVR_EMAIL, "password": PVR_PASSWORD},
            )
            pvr_token = login_resp.json().get("token") if login_resp.status_code == 200 else None

            # Get current showtimes from PVR
            st_resp = await client.get(f"{PVR_URL}/v1/showtimes")
            pvr_showtimes = st_resp.json()
        except Exception as e:
            print(f"Error connecting to PVR ({PVR_URL}): {e}")
            return

    if not pvr_showtimes:
        print("No showtimes returned from PVR.")
        return

    print(f"2. Fetched {len(pvr_showtimes)} live showtime(s) from PVR.")

    async with AsyncSessionLocal() as session:
        # 3. Setup Partner
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

        # 4. Setup Venue & Screen
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

        # 5. Setup Provider Registry
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

        # 6. Clean out stale showtimes that do not match current PVR IDs
        current_pvr_ids = [st["id"] for st in pvr_showtimes]
        await session.execute(
            delete(Showtime).where(
                Showtime.provider_id == provider.id,
                Showtime.provider_showtime_ref.notin_(current_pvr_ids),
            )
        )

        # 7. Create or update showtimes linked to PVR
        for st in pvr_showtimes:
            title = st["movie_title"]
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
                    poster_url="https://images.pexels.com/photos/20151747/pexels-photo-20151747.jpeg?auto=compress&cs=tinysrgb&h=500&w=350",
                    synopsis=f"Now showing at PVR Cinemas: {title}",
                )
                session.add(movie)
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
            else:
                existing_st.starts_at = starts_at_dt
                existing_st.provider_id = provider.id
                existing_st.status = "ACTIVE"

        await session.commit()
        print(f"3. Successfully synced {len(pvr_showtimes)} showtimes directly to PVR!")

if __name__ == "__main__":
    asyncio.run(sync_production())
