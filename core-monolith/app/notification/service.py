from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.notification.models import UserDeviceTokenModel, UserNotificationModel
from app.shared.timeutil import utcnow

logger = logging.getLogger(__name__)

# Real-time in-memory SSE pub/sub queues per user_id
_user_streams: dict[str, set[asyncio.Queue[dict[str, Any]]]] = defaultdict(set)
_fcm_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


def subscribe_user_stream(user_id: UUID) -> asyncio.Queue[dict[str, Any]]:
    q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=50)
    _user_streams[str(user_id)].add(q)
    return q


def unsubscribe_user_stream(user_id: UUID, q: asyncio.Queue[dict[str, Any]]) -> None:
    key = str(user_id)
    if key in _user_streams:
        _user_streams[key].discard(q)
        if not _user_streams[key]:
            _user_streams.pop(key, None)


def publish_realtime_notification(user_id: UUID, payload: dict[str, Any]) -> None:
    queues = list(_user_streams.get(str(user_id), ()))
    for q in queues:
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass


def format_relative_time(dt: datetime | None) -> str:
    if not dt:
        return "Just now"
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff_sec = max(0, int((now - dt).total_seconds()))
    if diff_sec < 60:
        return "Just now"
    if diff_sec < 3600:
        mins = diff_sec // 60
        return f"{mins} min{'s' if mins != 1 else ''} ago"
    if diff_sec < 86400:
        hrs = diff_sec // 3600
        return f"{hrs} hour{'s' if hrs != 1 else ''} ago"
    days = diff_sec // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


async def _get_fcm_access_token(sa_info: dict[str, Any]) -> Optional[str]:
    now = time.time()
    if _fcm_token_cache["access_token"] and _fcm_token_cache["expires_at"] > now + 60:
        return _fcm_token_cache["access_token"]

    client_email = sa_info.get("client_email")
    private_key = sa_info.get("private_key")
    token_uri = sa_info.get("token_uri", "https://oauth2.googleapis.com/token")
    if not client_email or not private_key:
        return None

    iat = int(now)
    exp = iat + 3600
    assertion = jwt.encode(
        {
            "iss": client_email,
            "scope": "https://www.googleapis.com/auth/firebase.messaging",
            "aud": token_uri,
            "iat": iat,
            "exp": exp,
        },
        private_key,
        algorithm="RS256",
    )

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            token_uri,
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": assertion,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        access_token = data.get("access_token")
        if access_token:
            _fcm_token_cache["access_token"] = access_token
            _fcm_token_cache["expires_at"] = now + int(data.get("expires_in", 3600))
        return access_token


async def send_fcm_push_to_tokens(
    tokens: list[str],
    title: str,
    body: str,
    link: Optional[str] = None,
) -> None:
    raw_sa = getattr(settings, "FIREBASE_SERVICE_ACCOUNT_JSON", None)
    if not raw_sa or not tokens:
        return

    try:
        sa_info = json.loads(raw_sa)
        project_id = sa_info.get("project_id") or settings.FIREBASE_PROJECT_ID
        if not project_id:
            return
        access_token = await _get_fcm_access_token(sa_info)
        if not access_token:
            return

        url = f"https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            for token in tokens:
                message_payload: dict[str, Any] = {
                    "message": {
                        "token": token,
                        "notification": {
                            "title": title,
                            "body": body,
                        },
                        "data": {
                            "link": link or "/profile?tab=orders",
                            "title": title,
                            "body": body,
                        },
                    }
                }
                try:
                    await client.post(url, headers=headers, json=message_payload)
                except Exception as exc:
                    logger.debug("FCM send failed for token %s...: %s", token[:12], exc)
    except Exception as exc:
        logger.warning("FCM push dispatch failed: %s", exc)


async def create_user_notification(
    session: Optional[AsyncSession],
    user_id: Optional[UUID],
    title: str,
    description: Optional[str] = None,
    notif_type: str = "booking",
    link: Optional[str] = None,
    reference_key: Optional[str] = None,
    commit: bool = False,
    *,
    body: Optional[str] = None,
    category: Optional[str] = None,
) -> Optional[UserNotificationModel]:
    """
    Safely creates an in-app notification for a user, broadcasts it in real time
    over SSE, and dispatches FCM push notifications to registered user devices.
    """
    if not session or not user_id:
        return None

    desc_text = description if description is not None else (body or "")
    resolved_type = category if category is not None else notif_type
    resolved_link = link or ("/profile?tab=orders" if resolved_type == "booking" else None)

    device_tokens: list[str] = []

    try:
        async with session.begin_nested():
            if reference_key:
                existing = (
                    await session.execute(
                        select(UserNotificationModel).where(
                            UserNotificationModel.user_id == user_id,
                            UserNotificationModel.reference_key == reference_key,
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    return existing

            notif = UserNotificationModel(
                id=uuid.uuid4(),
                user_id=user_id,
                title=title,
                description=desc_text,
                type=resolved_type,
                link=resolved_link,
                is_read=False,
                reference_key=reference_key,
                created_at=utcnow(),
            )
            session.add(notif)
            await session.flush()

            try:
                token_rows = (
                    await session.execute(
                        select(UserDeviceTokenModel.fcm_token).where(
                            UserDeviceTokenModel.user_id == user_id
                        )
                    )
                ).scalars().all()
                device_tokens = [t for t in token_rows if t]
            except Exception:
                device_tokens = []

        if commit:
            await session.commit()

        realtime_payload = {
            "id": str(notif.id),
            "title": notif.title,
            "description": notif.description,
            "time": "Just now",
            "read": False,
            "type": notif.type if notif.type in ("booking", "offer", "update") else "booking",
            "link": notif.link,
            "created_at": notif.created_at.isoformat() if notif.created_at else None,
        }
        publish_realtime_notification(user_id, realtime_payload)

        if device_tokens:
            try:
                asyncio.create_task(
                    send_fcm_push_to_tokens(
                        tokens=device_tokens,
                        title=notif.title,
                        body=notif.description,
                        link=notif.link,
                    )
                )
            except RuntimeError:
                pass

        return notif
    except Exception as exc:
        logger.warning("Could not persist in-app notification for user %s: %s", user_id, exc)
        return None
