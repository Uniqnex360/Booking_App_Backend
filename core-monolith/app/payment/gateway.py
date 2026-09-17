"""
Razorpay Gateway — the ONLY file allowed to import httpx or read RAZORPAY secrets.
"""
import hmac
import hashlib
import logging
import httpx
from app.core.config import settings
from app.payment.interfaces import GatewayUnavailable, VerificationFailed

logger = logging.getLogger(__name__)

PAYMENT_WINDOW_SECONDS = 300


def _get_key_id() -> str:
    return getattr(settings, "RAZORPAY_KEY_ID", "rzp_test_VyBhZExTMTk5")


def _get_key_secret() -> str:
    return getattr(settings, "RAZORPAY_KEY_SECRET", "test_secret_placeholder")


def _get_webhook_secret() -> str:
    return getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "whsec_test_placeholder")


def verify_boot_config():
    env = getattr(settings, "RAZORPAY_ENV", "test")
    key_id = _get_key_id()
    if env == "test" and not key_id.startswith("rzp_test_"):
        raise RuntimeError(
            f"RAZORPAY_ENV=test but RAZORPAY_KEY_ID starts with "
            f"'{key_id[:8]}...' instead of 'rzp_test_'. "
            f"Never use a live key in test mode."
        )


async def create_order(amount_paise: int, currency: str, receipt: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                "https://api.razorpay.com/v1/orders",
                json={
                    "amount": amount_paise,
                    "currency": currency,
                    "receipt": receipt,
                    "payment_capture": True,
                },
                auth=(_get_key_id(), _get_key_secret()),
            )
            if resp.status_code not in (200, 201):
                raise GatewayUnavailable(f"Razorpay order creation failed: {resp.status_code}")
            data = resp.json()
            return data["id"]
    except httpx.HTTPError as e:
        raise GatewayUnavailable(f"Razorpay unreachable: {e}")


async def fetch_payment(payment_id: str) -> dict:
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://api.razorpay.com/v1/payments/{payment_id}",
                    auth=(_get_key_id(), _get_key_secret()),
                )
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code >= 500 and attempt < 2:
                    continue
                raise GatewayUnavailable(f"Razorpay fetch failed: {resp.status_code}")
        except httpx.HTTPError as e:
            if attempt < 2:
                continue
            raise GatewayUnavailable(f"Razorpay unreachable: {e}")
    raise GatewayUnavailable("Razorpay fetch failed after retries")


def verify_signature(order_id: str, payment_id: str, signature: str) -> bool:
    message = f"{order_id}|{payment_id}"
    expected = hmac.new(
        _get_key_secret().encode(),
        message.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(body: bytes, signature: str) -> bool:
    expected = hmac.new(
        _get_webhook_secret().encode(),
        body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)

async def refund(payment_id: str, amount_paise: int, idempotency_key: str) -> str:
    """idempotency_key must be stable and deterministic per payment row (e.g. the
    payment's own UUID), never a fresh value per call. If the DB write after a
    successful refund crashes, the next sweep resends the SAME key and Razorpay
    returns the original refund instead of issuing a second one."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"https://api.razorpay.com/v1/payments/{payment_id}/refund",
                json={"amount": amount_paise},
                headers={"X-Razorpay-Idempotency": idempotency_key},
                auth=(_get_key_id(), _get_key_secret()),
            )
            if resp.status_code not in (200, 201):
                raise GatewayUnavailable(f"Razorpay refund failed: {resp.status_code}")
            data = resp.json()
            return data["id"]
    except httpx.HTTPError as e:
        raise GatewayUnavailable(f"Razorpay refund unreachable: {e}")
