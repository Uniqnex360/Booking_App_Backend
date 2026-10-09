import pytest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch
import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

from app.auth.interfaces import (
    User,
    UserRole,
    RefreshToken,
    PasswordResetRow,
    IUserRepository,
    IRefreshTokenRepository,
    IPasswordHasher,
    IPasswordResetRepository,
    INotificationService,
    IAuthenticationStrategy,
)
from app.auth.security import JWTTokenService, BcryptPasswordHasher
from app.auth.services import AuthService
from app.auth.strategies import FirebaseManualPhoneStrategy
from app.auth.exceptions import InvalidTokenError, TokenReuseError
from app.core.config import settings


@pytest.fixture
def token_service():
    return JWTTokenService()


@pytest.fixture
def sample_user():
    return User(
        id=uuid.uuid4(),
        full_name="Test User",
        email="test@example.com",
        phone="+919876543210",
        password_hash="$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW",
        role=UserRole.USER,
        is_active=True,
        is_verified=True,
    )


def test_access_token_creation_and_decoding(token_service, sample_user):
    token = token_service.create_access_token(sample_user)
    assert isinstance(token, str)

    payload = token_service.decode_token(token, token_type="access")
    assert payload["sub"] == str(sample_user.id)
    assert payload["role"] == "USER"
    assert payload["type"] == "access"
    assert "exp" in payload
    assert "iat" in payload


def test_refresh_token_creation_and_decoding(token_service, sample_user):
    family = uuid.uuid4()
    token = token_service.create_refresh_token(sample_user, family=family)
    assert isinstance(token, str)

    payload = token_service.decode_token(token, token_type="refresh")
    assert payload["sub"] == str(sample_user.id)
    assert payload["family"] == str(family)
    assert payload["type"] == "refresh"


def test_registration_token_creation_and_decoding(token_service):
    data = {"email": "pending@example.com", "code": "123456"}
    token = token_service.create_registration_token(data)
    assert isinstance(token, str)

    payload = token_service.decode_token(token, token_type="registration")
    assert payload["email"] == "pending@example.com"
    assert payload["code"] == "123456"
    assert payload["type"] == "registration"


def test_token_type_mismatch_rejected(token_service, sample_user):
    access_token = token_service.create_access_token(sample_user)
    with pytest.raises(InvalidTokenError, match="Invalid token type"):
        token_service.decode_token(access_token, token_type="refresh")


def test_expired_token_rejected(token_service, sample_user):
    token = token_service.create_access_token(sample_user, expires_delta=timedelta(seconds=-10))
    with pytest.raises(InvalidTokenError):
        token_service.decode_token(token)


def test_tampered_token_rejected(token_service, sample_user):
    token = token_service.create_access_token(sample_user)
    tampered = token[:-4] + "abcd"
    with pytest.raises(InvalidTokenError):
        token_service.decode_token(tampered)


def test_invalid_signature_with_different_key(token_service, sample_user):
    fake_token = jwt.encode(
        {"sub": str(sample_user.id), "type": "access"},
        "completely-different-secret-key-1234567890",
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        token_service.decode_token(fake_token)


# ==============================================================================
# SEC-09 Complete Flow Tests: Login, Refresh, Firebase, and Reset Flows
# ==============================================================================

@pytest.mark.asyncio
async def test_auth_login_flow(token_service, sample_user):
    """Verifies that login produces valid PyJWT access and refresh tokens."""
    user_repo = AsyncMock(spec=IUserRepository)
    token_repo = AsyncMock(spec=IRefreshTokenRepository)
    hasher = AsyncMock(spec=IPasswordHasher)
    strategy = AsyncMock(spec=IAuthenticationStrategy)
    strategy.authenticate.return_value = sample_user

    auth_service = AuthService(
        user_repo=user_repo,
        token_repo=token_repo,
        password_hasher=hasher,
        token_service=token_service,
        auth_strategy=strategy,
    )

    access_token, refresh_token = await auth_service.login("test@example.com", "SecretPass123!")
    assert access_token is not None
    assert refresh_token is not None

    access_payload = token_service.decode_token(access_token, token_type="access")
    assert access_payload["sub"] == str(sample_user.id)

    refresh_payload = token_service.decode_token(refresh_token, token_type="refresh")
    assert refresh_payload["sub"] == str(sample_user.id)
    assert "family" in refresh_payload
    token_repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_auth_refresh_flow_and_reuse_detection(token_service, sample_user):
    """Verifies token rotation and family-based revocation on reuse."""
    user_repo = AsyncMock(spec=IUserRepository)
    user_repo.get_by_id.return_value = sample_user

    token_repo = AsyncMock(spec=IRefreshTokenRepository)
    hasher = AsyncMock(spec=IPasswordHasher)
    strategy = AsyncMock(spec=IAuthenticationStrategy)

    family_id = uuid.uuid4()
    initial_refresh = token_service.create_refresh_token(sample_user, family=family_id)
    initial_hash = auth_service_hash = token_service.hash_token(initial_refresh)

    db_token = RefreshToken(
        id=uuid.uuid4(),
        user_id=sample_user.id,
        token_hash=initial_hash,
        token_family=family_id,
        expires_at=datetime.utcnow() + timedelta(days=7),
        is_revoked=False,
    )
    token_repo.get_by_hash.return_value = db_token

    auth_service = AuthService(
        user_repo=user_repo,
        token_repo=token_repo,
        password_hasher=hasher,
        token_service=token_service,
        auth_strategy=strategy,
    )

    # 1. Valid refresh produces new tokens and revokes old
    new_access, new_refresh = await auth_service.refresh_token(initial_refresh)
    assert new_access is not None
    assert new_refresh is not None
    token_repo.revoke.assert_awaited_once_with(initial_hash)

    # 2. Token reuse attack: already revoked token presented
    revoked_token = RefreshToken(
        id=uuid.uuid4(),
        user_id=sample_user.id,
        token_hash=initial_hash,
        token_family=family_id,
        expires_at=datetime.utcnow() + timedelta(days=7),
        is_revoked=True,
    )
    token_repo.get_by_hash.return_value = revoked_token
    with pytest.raises(TokenReuseError):
        await auth_service.refresh_token(initial_refresh)


@pytest.mark.asyncio
async def test_firebase_flow_with_pyjwt(monkeypatch):
    """Verifies Firebase RS256 token verification and decoding using PyJWT."""
    # Generate RSA test key pair
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")

    project_id = "test-firebase-proj"
    kid = "test-key-id-123"

    payload = {
        "aud": project_id,
        "iss": f"https://securetoken.google.com/{project_id}",
        "sub": "firebase-uid-abc",
        "phone_number": "+919876543210",
        "name": "Firebase User",
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }

    token = jwt.encode(payload, private_key, algorithm="RS256", headers={"kid": kid})

    user_repo = AsyncMock(spec=IUserRepository)
    user_repo.get_by_phone.return_value = None  # Will auto-register
    user_repo.create.side_effect = lambda u: u

    strategy = FirebaseManualPhoneStrategy(user_repo=user_repo, project_id=project_id)
    monkeypatch.setattr(strategy, "_get_google_public_keys", AsyncMock(return_value={kid: public_pem}))
    user = await strategy.authenticate({"token": token})

    assert user is not None
    assert user.phone == "+919876543210"
    assert user.full_name == "Firebase User"
    user_repo.create.assert_awaited_once()


@pytest.mark.asyncio
async def test_password_reset_flow(token_service, sample_user):
    """Verifies password reset token creation, validation, and execution."""
    user_repo = AsyncMock(spec=IUserRepository)
    user_repo.get_by_email.return_value = sample_user
    user_repo.get_by_id.return_value = sample_user

    token_repo = AsyncMock(spec=IRefreshTokenRepository)
    reset_repo = AsyncMock(spec=IPasswordResetRepository)
    notification = AsyncMock(spec=INotificationService)
    hasher = BcryptPasswordHasher()

    auth_service = AuthService(
        user_repo=user_repo,
        token_repo=token_repo,
        password_hasher=hasher,
        token_service=token_service,
        auth_strategy=AsyncMock(),
    )

    # 1. Request reset
    await auth_service.request_password_reset(sample_user.email, reset_repo, notification)
    reset_repo.create.assert_awaited_once()
    notification.send_email.assert_awaited_once()

    captured_token_hash = reset_repo.create.call_args[0][1]

    # 2. Validate reset token
    fake_row = PasswordResetRow(
        id=uuid.uuid4(),
        user_id=sample_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        used_at=None,
    )
    reset_repo.get_valid.return_value = fake_row

    # 3. Complete reset
    success = await auth_service.reset_password(
        reset_repo=reset_repo,
        refresh_repo=token_repo,
        hasher=hasher,
        raw_token="raw-token-string",
        new_password="NewSecurePassword123!",
    )
    assert success is True
    assert hasher.verify("NewSecurePassword123!", sample_user.password_hash)
    reset_repo.mark_used.assert_awaited_once()
    token_repo.revoke_all_for_user.assert_awaited_once_with(sample_user.id)
