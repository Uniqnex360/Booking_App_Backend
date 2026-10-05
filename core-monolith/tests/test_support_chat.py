import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_support_chat_knowledge_base_fallback():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Test refund query
        res = await client.post(
            "/v1/support/chat",
            json={
                "message": "Where is my refund for cancelled tickets?",
                "category": "Payment & Refund",
                "history": []
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert "reply" in data
        assert len(data["reply"]) > 10
        assert "refund" in data["reply"].lower() or "upi" in data["reply"].lower()

@pytest.mark.asyncio
async def test_support_chat_cancellation_query():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/support/chat",
            json={
                "message": "How do I cancel my booking?",
                "category": "Cancellation/Exchange request",
                "history": []
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert "cancel" in data["reply"].lower()
        assert "profile" in data["reply"].lower()

@pytest.mark.asyncio
async def test_support_chat_validation_error():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Empty message should fail validation with 422
        res = await client.post(
            "/v1/support/chat",
            json={"message": ""}
        )
        assert res.status_code == 422

@pytest.mark.asyncio
async def test_support_chat_guest_personal_booking_query():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.post(
            "/v1/support/chat",
            json={
                "message": "What is my booking status?",
                "history": []
            }
        )
        assert res.status_code == 200
        data = res.json()
        assert "reply" in data
        assert "log in" in data["reply"].lower() or "purchase history" in data["reply"].lower()

def test_personalized_knowledge_base_fallback():
    from app.support.service import get_knowledge_base_fallback

    # 1. User with active booking asks about booking
    mock_bookings = [
        {
            "id": "b1",
            "ref_code": "VYHBZ-1234",
            "type": "MOVIE",
            "title": "Kalki 2898 AD",
            "venue": "PVR Forum • Screen 2",
            "location": "Kochi",
            "date": "10 Oct 2026, 06:30 PM",
            "seats": ["D10", "D11"],
            "quantity": 2,
            "total_rupees": 540,
            "status": "CONFIRMED",
        }
    ]
    reply = get_knowledge_base_fallback(
        query="What is my booking?",
        user_name="John Doe",
        user_bookings=mock_bookings,
    )
    assert "Kalki 2898 AD" in reply
    assert "VYHBZ-1234" in reply
    assert "D10, D11" in reply

    # 2. User asks about their seats
    seat_reply = get_knowledge_base_fallback(
        query="Which seats do I have?",
        user_name="John Doe",
        user_bookings=mock_bookings,
    )
    assert "D10, D11" in seat_reply
    assert "Kalki 2898 AD" in seat_reply

    # 3. User with no bookings
    empty_reply = get_knowledge_base_fallback(
        query="Show my tickets",
        user_name="Jane",
        user_bookings=[],
    )
    assert "don't have any bookings" in empty_reply.lower()

@pytest.mark.asyncio
async def test_support_chat_authenticated_personal_query(monkeypatch):
    import uuid
    from app.auth.interfaces import User as AuthUserDomain, UserRole
    from app.auth.dependencies import get_current_user_optional

    mock_user = AuthUserDomain(
        id=uuid.uuid4(),
        full_name="Alice Smith",
        email="alice@example.com",
        role=UserRole.USER,
        is_active=True,
        password_hash="hash",
    )

    async def mock_recent_bookings(*args, **kwargs):
        return [
            {
                "id": "b-99",
                "ref_code": "VYHBZ-ALICE",
                "type": "MOVIE",
                "title": "Interstellar Re-release",
                "venue": "PVR IMAX",
                "location": "Kochi",
                "date": "15 Oct 2026, 08:00 PM",
                "seats": ["F1", "F2"],
                "quantity": 2,
                "total_rupees": 700,
                "status": "CONFIRMED",
            }
        ]

    import app.support.routes as routes_module
    monkeypatch.setattr(routes_module, "get_user_recent_bookings", mock_recent_bookings)

    app.dependency_overrides[get_current_user_optional] = lambda: mock_user
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/v1/support/chat",
                json={
                    "message": "What is my booking?",
                    "history": []
                }
            )
            assert res.status_code == 200
            data = res.json()
            assert "Interstellar Re-release" in data["reply"]
            assert "VYHBZ-ALICE" in data["reply"]
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)

