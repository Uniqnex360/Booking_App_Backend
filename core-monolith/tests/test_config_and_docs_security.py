import pytest
from unittest.mock import patch
from app.core.config import Settings


def test_production_requires_explicit_jwt_secret():
    # When ENVIRONMENT is production and JWT_SECRET_KEY is missing, it must fail validation
    with pytest.raises((ValueError, RuntimeError), match="JWT_SECRET_KEY must be explicitly configured in production"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
            CORS_ORIGINS="*",
            FRONTEND_URL="http://localhost",
            JWT_SECRET_KEY=None,
        )


def test_production_disables_docs_endpoints(monkeypatch):
    from fastapi import FastAPI
    from app.core.config import settings
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    is_prod = settings.ENVIRONMENT.lower() == "production"
    test_app = FastAPI(
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )
    assert test_app.docs_url is None
    assert test_app.redoc_url is None
    assert test_app.openapi_url is None
