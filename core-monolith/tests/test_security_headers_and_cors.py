import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_cors_rejects_arbitrary_vercel_subdomains():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.options(
            "/health",
            headers={
                "Origin": "https://malicious-attacker.vercel.app",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "https://malicious-attacker.vercel.app"


@pytest.mark.asyncio
async def test_cors_allows_capacitor_and_localhost_origins():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for origin in ["capacitor://localhost", "https://localhost", "http://localhost:5173"]:
            resp = await ac.options(
                "/health",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                },
            )
            assert resp.headers.get("access-control-allow-origin") == origin


@pytest.mark.asyncio
async def test_security_headers_present():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
