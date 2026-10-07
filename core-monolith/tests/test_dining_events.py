import uuid
import pytest
from datetime import datetime, timedelta, timezone
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from jose import jwt

from app.main import app
from app.core.config import settings
from app.core.database import get_db
from app.auth.models import User as UserORM
from app.partner.models import PartnerORM
from app.event.models import EventORM, TicketCategoryORM
from app.event.interfaces import EventCategory, EventStatus

def _token_for(user_id: uuid.UUID, role: str = "PARTNER") -> str:
    to_encode = {
        "sub": str(user_id),
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

@pytest.mark.asyncio
async def test_dining_events_listing_and_filters(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    # 1. Create a partner and dining event
    partner_user = UserORM(
        id=uuid.uuid4(),
        full_name="Dining Host",
        email=f"host_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="PARTNER",
        is_active=True,
    )
    session.add(partner_user)

    partner = PartnerORM(
        id=uuid.uuid4(),
        user_id=partner_user.id,
        business_name="Aqua Hospitality",
        partner_type="restaurant",
        contact_name="Dining Host",
        contact_phone="9876543210",
        city="Kochi",
        status="APPROVED",
    )
    session.add(partner)
    await session.commit()

    now = datetime.now(timezone.utc)
    dining_event = EventORM(
        id=uuid.uuid4(),
        partner_id=partner.id,
        title="Seaside Sunday Brunch",
        slug=f"seaside-brunch-{uuid.uuid4().hex[:6]}",
        category=EventCategory.DINING.value,
        venue_name="Aqua Vista",
        city="Kochi",
        starts_at=now + timedelta(hours=2),
        ends_at=now + timedelta(hours=5),
        status=EventStatus.PUBLISHED.value,
        poster_image_url="https://example.com/poster.jpg",
        cuisine=["Continental", "Italian"],
        price_range=3,
        what_included="Buffet spread with unlimited mocktails",
        tags=["SUNDAY_BRUNCH", "POOLSIDE"],
    )
    session.add(dining_event)

    concert_event = EventORM(
        id=uuid.uuid4(),
        partner_id=partner.id,
        title="Rock Night Live",
        slug=f"rock-night-{uuid.uuid4().hex[:6]}",
        category=EventCategory.CONCERT.value,
        venue_name="Arena One",
        city="Kochi",
        starts_at=now + timedelta(days=2),
        ends_at=now + timedelta(days=2, hours=3),
        status=EventStatus.PUBLISHED.value,
        poster_image_url="https://example.com/rock.jpg",
        tags=["LIVE_MUSIC"],
    )
    session.add(concert_event)

    # Add ticket category for dining event (price: 1500 INR = 150000 paise)
    ticket_cat = TicketCategoryORM(
        id=uuid.uuid4(),
        event_id=dining_event.id,
        name="Brunch Pass",
        price_paise=150000,
        capacity=50,
        is_active=True,
    )
    session.add(ticket_cat)
    await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Filter by category=dining
        res = await client.get("/v1/events?category=dining")
        assert res.status_code == 200
        events = res.json()["data"]["items"]
        dining_ids = [e["id"] for e in events]
        assert str(dining_event.id) in dining_ids
        assert str(concert_event.id) not in dining_ids

        # Check dining fields returned in detail / listing
        target = next(e for e in events if e["id"] == str(dining_event.id))
        assert target["category"] == "dining"
        assert target["cuisine"] == ["Continental", "Italian"]
        assert target["price_range"] == 3
        assert target["what_included"] == "Buffet spread with unlimited mocktails"
        assert target["min_price_paise"] == 150000

        # Filter by tag
        res_tag = await client.get("/v1/events?category=dining&tags=SUNDAY_BRUNCH")
        assert res_tag.status_code == 200
        assert any(e["id"] == str(dining_event.id) for e in res_tag.json()["data"]["items"])

        # Filter by date=today
        res_date = await client.get("/v1/events?category=dining&date=today")
        assert res_date.status_code == 200
        assert any(e["id"] == str(dining_event.id) for e in res_date.json()["data"]["items"])

        # Filter by price=500-2000 (1500 is in range)
        res_price = await client.get("/v1/events?category=dining&price=500-2000")
        assert res_price.status_code == 200
        assert any(e["id"] == str(dining_event.id) for e in res_price.json()["data"]["items"])

        # Filter by price=0-500 (1500 is NOT in range)
        res_price_low = await client.get("/v1/events?category=dining&price=0-500")
        assert res_price_low.status_code == 200
        assert not any(e["id"] == str(dining_event.id) for e in res_price_low.json()["data"]["items"])

    app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_partner_create_dining_event(session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: session

    # Create partner user and partner record with restaurant type
    partner_user = UserORM(
        id=uuid.uuid4(),
        full_name="Bistro Owner",
        email=f"bistro_{uuid.uuid4().hex[:6]}@test.com",
        password_hash="hash",
        role="PARTNER",
        is_active=True,
    )
    session.add(partner_user)

    partner = PartnerORM(
        id=uuid.uuid4(),
        user_id=partner_user.id,
        business_name="Bistro Royale",
        partner_type="restaurant",
        contact_name="Bistro Owner",
        contact_phone="9876543210",
        city="Kochi",
        status="APPROVED",
    )
    session.add(partner)
    await session.commit()

    token = _token_for(partner_user.id, role="PARTNER")

    now = datetime.now(timezone.utc)
    payload = {
        "title": "Chef's Tasting Dinner",
        "category": "dining",
        "venue_name": "Bistro Royale",
        "city": "Kochi",
        "starts_at": (now + timedelta(days=1)).isoformat(),
        "ends_at": (now + timedelta(days=1, hours=3)).isoformat(),
        "poster_image_url": "https://example.com/dinner.jpg",
        "description": "5-course curated dining experience",
        "cuisine": ["French", "European"],
        "price_range": 4,
        "what_included": "5 courses with pairing mocktails",
        "tags": ["FINE_DINING", "ROOFTOP"],
        "ticket_categories": [
            {
                "name": "Standard Experience",
                "price_paise": 250000,
                "capacity": 20,
            }
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.post(
            "/v1/partner/events",
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        assert res.status_code == 201
        data = res.json()["data"]
        assert data["title"] == "Chef's Tasting Dinner"
        assert data["category"] == "dining"
        assert data["cuisine"] == ["French", "European"]
        assert data["price_range"] == 4
        assert data["what_included"] == "5 courses with pairing mocktails"
        assert "FINE_DINING" in data["tags"]

    app.dependency_overrides.clear()
