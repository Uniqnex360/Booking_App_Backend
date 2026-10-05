import pytest
from httpx import AsyncClient, ASGITransport, Response, Request
from unittest.mock import patch
from app.main import app
from app.core.config import settings

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
        assert data["source"] == "knowledge_base"
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
        assert data["source"] == "knowledge_base"
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
async def test_support_chat_with_mock_openai_success():
    from httpx import AsyncClient as AC
    original_post = AC.post

    async def mock_post(self, url, *args, **kwargs):
        if "api.openai.com" in str(url):
            return Response(
                200,
                json={"choices": [{"message": {"content": "Hello! I can help you with your cancellation."}}]},
                request=Request("POST", url)
            )
        return await original_post(self, url, *args, **kwargs)

    with patch.object(AC, "post", new=mock_post):
        settings.OPENAI_API_KEY = "sk-test-valid-key"
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.post(
                "/v1/support/chat",
                json={"message": "Can I cancel my ticket?", "category": "Cancellation"}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["source"] == "ai"
            assert "Hello!" in data["reply"]
        settings.OPENAI_API_KEY = None
