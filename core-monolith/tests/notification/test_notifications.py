import uuid
from datetime import datetime, timedelta, timezone
import pytest

from app.notification.service import (
    format_relative_time,
    publish_realtime_notification,
    subscribe_user_stream,
    unsubscribe_user_stream,
)


def test_format_relative_time():
    now = datetime.now(timezone.utc)
    assert format_relative_time(now - timedelta(seconds=15)) == "Just now"
    assert format_relative_time(now - timedelta(minutes=5)) == "5 mins ago"
    assert format_relative_time(now - timedelta(hours=2)) == "2 hours ago"
    assert format_relative_time(now - timedelta(days=3)) == "3 days ago"


def test_realtime_stream_pubsub():
    user_id = uuid.uuid4()
    queue = subscribe_user_stream(user_id)
    try:
        payload = {"id": "123", "title": "Booking Confirmed! 🎉"}
        publish_realtime_notification(user_id, payload)
        assert not queue.empty()
        received = queue.get_nowait()
        assert received == payload
    finally:
        unsubscribe_user_stream(user_id, queue)
