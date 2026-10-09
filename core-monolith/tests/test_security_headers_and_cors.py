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
async def test_cors_rejects_null_origin():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.options(
            "/health",
            headers={
                "Origin": "null",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") != "null"


@pytest.mark.asyncio
async def test_cors_allows_production_web_origin():
    from app.core.config import settings
    prod_origin = getattr(settings, "FRONTEND_URL", "https://booking-app-frontend-navy.vercel.app")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.options(
            "/health",
            headers={
                "Origin": prod_origin,
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp.headers.get("access-control-allow-origin") == prod_origin


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
        assert resp.headers.get("Referrer-Policy") == "no-referrer"


@pytest.mark.asyncio
async def test_cors_production_environment_blocks_insecure_localhost_and_allows_capacitor():
    from app.main import create_app
    prod_app = create_app(environment="production")
    async with AsyncClient(transport=ASGITransport(app=prod_app), base_url="http://test") as ac:
        # http://localhost:5173 must be rejected in production
        resp_dev = await ac.options(
            "/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp_dev.headers.get("access-control-allow-origin") != "http://localhost:5173"

        # http://127.0.0.1:8000 must be rejected in production
        resp_loopback = await ac.options(
            "/health",
            headers={
                "Origin": "http://127.0.0.1:8000",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp_loopback.headers.get("access-control-allow-origin") != "http://127.0.0.1:8000"

        # capacitor://localhost must be allowed in production
        resp_cap = await ac.options(
            "/health",
            headers={
                "Origin": "capacitor://localhost",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp_cap.headers.get("access-control-allow-origin") == "capacitor://localhost"

        # https://localhost must be allowed in production
        resp_https_local = await ac.options(
            "/health",
            headers={
                "Origin": "https://localhost",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert resp_https_local.headers.get("access-control-allow-origin") == "https://localhost"

