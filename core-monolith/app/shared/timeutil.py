"""
Timezone-aware SQLAlchemy TypeDecorator and UTC time helpers.
"""

from datetime import datetime, timezone
from sqlalchemy import types


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_aware_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class TZDateTime(types.TypeDecorator):
    """
    SQLAlchemy TypeDecorator that guarantees timezone-aware UTC datetimes
    on read/write, even on SQLite where CURRENT_TIMESTAMP returns naive strings.
    """

    impl = types.DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None:
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        return value
