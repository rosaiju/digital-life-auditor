from datetime import datetime, timezone


def utcnow() -> datetime:
    """Naive UTC timestamp (columns are stored as timezone-less UTC)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
