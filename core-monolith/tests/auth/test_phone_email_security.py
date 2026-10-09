import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.auth.strategies import PhoneEmailStrategy
from app.auth.exceptions import InvalidCredentialsError


@pytest.mark.asyncio
async def test_phone_email_rejects_untrusted_domain():
    user_repo = AsyncMock()
    strategy = PhoneEmailStrategy(user_repo)
    
    # Attacker host must be rejected immediately without making request
    with pytest.raises(InvalidCredentialsError, match="Invalid Phone.Email verification URL"):
        await strategy.authenticate({"url": "https://attacker.com/user.json"})


@pytest.mark.asyncio
async def test_phone_email_rejects_http_scheme():
    user_repo = AsyncMock()
    strategy = PhoneEmailStrategy(user_repo)
    
    with pytest.raises(InvalidCredentialsError, match="Invalid Phone.Email verification URL"):
        await strategy.authenticate({"url": "http://auth.phone.email/user.json"})


@pytest.mark.asyncio
async def test_phone_email_rejects_private_and_loopback_ips():
    user_repo = AsyncMock()
    strategy = PhoneEmailStrategy(user_repo)
    
    for url in [
        "http://127.0.0.1:8000/api",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.1/admin",
        "http://192.168.1.1/secret",
        "http://localhost:8000/debug",
    ]:
        with pytest.raises(InvalidCredentialsError):
            await strategy.authenticate({"url": url})


@pytest.mark.asyncio
async def test_phone_email_rejects_redirects():
    user_repo = AsyncMock()
    strategy = PhoneEmailStrategy(user_repo)
    
    # Simulate a redirect response from auth.phone.email
    mock_resp = MagicMock()
    mock_resp.is_redirect = True
    mock_resp.status_code = 302
    mock_resp.headers = {"location": "http://169.254.169.254/latest/meta-data"}
    
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        with pytest.raises(InvalidCredentialsError, match="redirects not allowed"):
            await strategy.authenticate({"url": "https://auth.phone.email/user_json_url/redirect"})


@pytest.mark.asyncio
async def test_phone_email_valid_request():
    user_repo = AsyncMock()
    user_repo.get_by_phone.return_value = None
    user_repo.create.return_value = MagicMock(id="123", phone="+919876543210")
    strategy = PhoneEmailStrategy(user_repo)
    
    mock_resp = MagicMock()
    mock_resp.is_redirect = False
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/json"}
    mock_resp.json.return_value = {
        "user_country_code": "+91",
        "user_phone_number": "9876543210",
        "user_first_name": "Test",
        "user_last_name": "User",
    }
    
    # Mock DNS resolution to public IP
    with patch("socket.getaddrinfo", return_value=[(None, None, None, None, ("104.21.50.1", 443))]), \
         patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_resp
        user = await strategy.authenticate({"url": "https://auth.phone.email/user_json_url/valid123"})
        assert user is not None
        user_repo.create.assert_awaited_once()
