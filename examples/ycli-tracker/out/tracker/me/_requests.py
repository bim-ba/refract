"""Request builders for Tracker me - the single HTTP contract (sans-I/O)."""

from ycli.yandex.tracker.runtime import Request

from .models import Me


def get() -> Request[Me]:
    """``GET /myself`` -> Me request builder."""
    return Request(method="GET", path="myself", response_model=Me)
