import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

import app.auth.models  # ensure models are registered with Base.metadata
from app.main import app  # ensure all models and routes are imported
from app.auth.strategies import PhoneEmailStrategy
from app.auth.exceptions import InvalidCredentialsError


@pytest.fixture
def user_repo():
    repo = AsyncMock()
    repo.get_by_phone.return_value = None
    repo.create.side_effect = lambda u: u
    repo.update_last_login.return_value = None
    repo.is_verification_url_used.return_value = False
    repo.mark_verification_url_used.return_value = None
    return repo


@pytest.mark.asyncio
async def test_phone_email_rejects_untrusted_domain(user_repo):
    strategy = PhoneEmailStrategy(user_repo)
    with pytest.raises(InvalidCredentialsError, match="untrusted domain"):
        await strategy.authenticate({"url": "https://attacker.com/user.json"})


@pytest.mark.asyncio
async def test_phone_email_rejects_http_scheme(user_repo):
    strategy = PhoneEmailStrategy(user_repo)
    with pytest.raises(InvalidCredentialsError, match="HTTPS required"):
        await strategy.authenticate({"url": "http://user.phone.email/user.json"})


@pytest.mark.asyncio
async def test_phone_email_rejects_redirects(user_repo):
    strategy = PhoneEmailStrategy(user_repo)
    mock_resp = MagicMock()
    mock_resp.is_redirect = True
    mock_resp.status_code = 302

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(InvalidCredentialsError, match="redirects not allowed"):
            await strategy.authenticate({"url": "https://user.phone.email/user_123.json"})


@pytest.mark.asyncio
async def test_phone_email_handles_timeout(user_repo):
    strategy = PhoneEmailStrategy(user_repo)

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Connection timed out")
        with pytest.raises(InvalidCredentialsError, match="network error"):
            await strategy.authenticate({"url": "https://user.phone.email/user_timeout.json"})


@pytest.mark.asyncio
async def test_phone_email_handles_non_200(user_repo):
    strategy = PhoneEmailStrategy(user_repo)
    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 404

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(InvalidCredentialsError, match="HTTP 404"):
            await strategy.authenticate({"url": "https://user.phone.email/user_404.json"})


@pytest.mark.asyncio
async def test_phone_email_handles_bad_json(user_repo):
    strategy = PhoneEmailStrategy(user_repo)
    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.json.side_effect = ValueError("Expecting value: line 1 column 1")

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(InvalidCredentialsError, match="malformed JSON"):
            await strategy.authenticate({"url": "https://user.phone.email/user_bad_json.json"})


@pytest.mark.asyncio
async def test_phone_email_handles_missing_phone(user_repo):
    strategy = PhoneEmailStrategy(user_repo)
    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"user_first_name": "Test"}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(InvalidCredentialsError, match="missing phone details"):
            await strategy.authenticate({"url": "https://user.phone.email/user_no_phone.json"})


@pytest.mark.asyncio
async def test_phone_email_valid_payload_for_verified_hosts(user_repo):
    strategy = PhoneEmailStrategy(user_repo)

    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "user_country_code": "+91",
        "user_phone_number": "9876543210",
        "user_first_name": "Verified",
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        # Test user.phone.email (the verified JSON host from docs)
        user = await strategy.authenticate({"url": "https://user.phone.email/user_valid_001.json"})
        assert user is not None
        assert user.phone == "+919876543210"

        # Test auth.phone.email (also in verified allowlist)
        user2 = await strategy.authenticate({"url": "https://auth.phone.email/user_valid_002.json"})
        assert user2 is not None


@pytest.mark.asyncio
async def test_phone_email_replay_guard_rejects_reused_url(user_repo):
    strategy = PhoneEmailStrategy(user_repo)
    used_hashes = set()
    user_repo.is_verification_url_used.side_effect = lambda h: h in used_hashes
    def _mark(h, uid=None):
        used_hashes.add(h)
    user_repo.mark_verification_url_used.side_effect = _mark

    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "user_country_code": "+91",
        "user_phone_number": "9876543210",
    }

    url = "https://user.phone.email/user_single_use.json"
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        # First use succeeds
        user = await strategy.authenticate({"url": url})
        assert user is not None

        # Replay attempt fails
        with pytest.raises(InvalidCredentialsError, match="already been used"):
            await strategy.authenticate({"url": url})


@pytest.mark.asyncio
async def test_phone_email_failure_does_not_burn_url(user_repo):
    strategy = PhoneEmailStrategy(user_repo)
    url = "https://user.phone.email/user_retryable.json"
    used_hashes = set()
    user_repo.is_verification_url_used.side_effect = lambda h: h in used_hashes
    def _mark(h, uid=None):
        used_hashes.add(h)
    user_repo.mark_verification_url_used.side_effect = _mark

    # First attempt fails with network error
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Transient network failure")
        with pytest.raises(InvalidCredentialsError, match="network error"):
            await strategy.authenticate({"url": url})

    # Second attempt succeeds because the URL was not marked used on failure
    mock_success = MagicMock()
    mock_success.is_redirect = False
    mock_success.status_code = 200
    mock_success.json.return_value = {
        "user_country_code": "+91",
        "user_phone_number": "9876543210",
    }
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_success
        user = await strategy.authenticate({"url": url})
        assert user is not None
        assert user.phone == "+919876543210"


@pytest.mark.asyncio
async def test_phone_email_db_replay_guard_across_two_instances(engine):
    """Verifies that DB-backed replay guard works across two separate app instances/sessions."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from app.auth.repositories import SQLAlchemyUserRepository

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    url = "https://user.phone.email/user_multi_instance.json"

    # Instance 1 logs in successfully
    async with factory() as session1:
        repo1 = SQLAlchemyUserRepository(session1)
        strategy1 = PhoneEmailStrategy(repo1)

        mock_resp = MagicMock()
        mock_resp.is_redirect = False
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "user_country_code": "+91",
            "user_phone_number": "9123456789",
        }
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            user = await strategy1.authenticate({"url": url})
            assert user is not None
            assert user.phone == "+919123456789"

    # Instance 2 (completely separate session/strategy) attempts to replay the same URL
    async with factory() as session2:
        repo2 = SQLAlchemyUserRepository(session2)
        strategy2 = PhoneEmailStrategy(repo2)

        # Clear in-memory cache to prove DB table is the source of truth across instances
        if hasattr(PhoneEmailStrategy, "_replay_cache"):
            PhoneEmailStrategy._replay_cache.clear()

        mock_resp2 = MagicMock()
        mock_resp2.is_redirect = False
        mock_resp2.status_code = 200
        mock_resp2.json.return_value = {
            "user_country_code": "+91",
            "user_phone_number": "9123456789",
        }
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp2
            with pytest.raises(InvalidCredentialsError, match="already been used"):
                await strategy2.authenticate({"url": url})


@pytest.mark.asyncio
async def test_phone_email_parallel_requests_rejected(engine):
    """Two concurrent requests using the exact same verification URL: exactly one succeeds, the other fails."""
    import asyncio
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from app.auth.repositories import SQLAlchemyUserRepository

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    url = "https://user.phone.email/user_parallel_race.json"

    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "user_country_code": "+91",
        "user_phone_number": "9123456789",
    }

    async def attempt_auth():
        async with factory() as session:
            repo = SQLAlchemyUserRepository(session)
            strategy = PhoneEmailStrategy(repo)
            with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
                mock_get.return_value = mock_resp
                return await strategy.authenticate({"url": url})

    results = await asyncio.gather(attempt_auth(), attempt_auth(), return_exceptions=True)
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, InvalidCredentialsError)]

    assert len(successes) == 1
    assert len(failures) == 1
    assert "already been used" in str(failures[0])


@pytest.mark.asyncio
async def test_cleanup_old_verification_urls(engine):
    """Cleanup method purges expired verification URL records older than threshold."""
    import uuid
    from datetime import datetime, timezone, timedelta
    from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
    from app.auth.repositories import SQLAlchemyUserRepository
    from app.auth.models import UsedPhoneEmailVerification

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        repo = SQLAlchemyUserRepository(session)

        # Seed one recent record and one old record (25 hours ago)
        old_record = UsedPhoneEmailVerification(
            id=uuid.uuid4(),
            url_hash="old_hash_1234567890",
            created_at=datetime.now(timezone.utc) - timedelta(hours=25),
        )
        recent_record = UsedPhoneEmailVerification(
            id=uuid.uuid4(),
            url_hash="recent_hash_1234567890",
            created_at=datetime.now(timezone.utc),
        )
        session.add_all([old_record, recent_record])
        await session.commit()

        deleted_count = await repo.cleanup_old_verification_urls(max_age_hours=24)
        assert deleted_count == 1

        assert await repo.is_verification_url_used("old_hash_1234567890") is False
        assert await repo.is_verification_url_used("recent_hash_1234567890") is True


