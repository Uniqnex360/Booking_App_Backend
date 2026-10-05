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
