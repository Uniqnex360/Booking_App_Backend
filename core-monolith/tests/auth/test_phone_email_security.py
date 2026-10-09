import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from app.auth.strategies import PhoneEmailStrategy
from app.auth.exceptions import InvalidCredentialsError


@pytest.fixture
def user_repo():
    repo = AsyncMock()
    repo.get_by_phone.return_value = None
    repo.create.side_effect = lambda u: u
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
