"""Declarative Tracker priorities client - transport ONLY (thin sugar over request builders)."""

from ycli.yandex.tracker.base import TrackerResource

from . import _requests
from .models import Priority, PriorityCreate, PriorityList, PriorityUpdate


class PrioritiesClient(TrackerResource):
    """Declarative HTTP for ``/priorities`` (list + create + edit)."""

    def list(self) -> PriorityList:
        """``GET /priorities`` → priority listing.

        Example:
            >>> client = TrackerClient(oauth_token="…", organization_id="…")  # doctest: +SKIP
            >>> client.priorities.list().root[0].key  # doctest: +SKIP
            'normal'
        """
        return self._session.send(_requests.list_())

    def create(self, body: PriorityCreate) -> Priority:
        """Create a priority from a typed ``PriorityCreate`` body. Returns the new ``Priority``.

        Example:
            >>> client = TrackerClient(oauth_token="…", organization_id="…")  # doctest: +SKIP
            >>> client.priorities.create(
            ...     PriorityCreate(key="one", name=LocalizedName(ru="Низкий"), order=60)
            ... ).key  # doctest: +SKIP
            'one'
        """
        return self._session.send(_requests.create(body))

    def edit(
        self, priority_id: str, body: PriorityUpdate, *, version: int | None = None
    ) -> Priority:
        """Edit priority ``priority_id`` from a typed ``PriorityUpdate`` body.

        ``version`` is the current priority version; when set it is sent as ``?version=`` for
        optimistic locking (the API rejects a stale version with 409).

        Example:
            >>> client = TrackerClient(oauth_token="…", organization_id="…")  # doctest: +SKIP
            >>> client.priorities.edit(
            ...     "one", PriorityUpdate(name=LocalizedName(ru="Низкий")), version=1
            ... ).key  # doctest: +SKIP
            'one'
        """
        return self._session.send(_requests.edit(priority_id, body, version=version))
