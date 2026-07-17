"""Declarative Tracker /myself client - transport ONLY (thin sugar over request builders)."""

from ycli.yandex.tracker.base import TrackerResource

from . import _requests
from .models import Me


class MeClient(TrackerResource):
    """Declarative HTTP for ``/myself``."""

    def get(self) -> Me:
        """``GET /myself`` → the authenticated ``Me`` (a safe auth probe)."""
        return self._session.send(_requests.get())
