import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_forgot_password_does_not_enumerate_missing_user():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/v1/auth/forgot-password",
            json={"email": "nonexistent_random_user_12345@example.com"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "success"
        assert "If that account exists" in data.get("message", "")


@pytest.mark.asyncio
async def test_auth_rate_limit_enforced():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        responses = []
        for _ in range(6):
            r = await ac.post(
                "/v1/auth/forgot-password",
                json={"email": "ratelimit_test@example.com"},
            )
            responses.append(r.status_code)
        # Limiter is 3/minute on forgot-password, so 4th+ request must be 429
        assert 429 in responses
