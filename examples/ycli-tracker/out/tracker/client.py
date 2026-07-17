"""Tracker client - the composition root (aggregates resources, owns transport + auth)."""

from __future__ import annotations

import os

import httpx

from .me.client import MeClient
from .priorities.client import PrioritiesClient
from .runtime.auth import MultiHeaderAuth
from .runtime.session import Session


class TrackerClient:
    """Root client for the Tracker API."""

    def __init__(self, *, oauth_token: str, organization_id: str) -> None:
        auth = MultiHeaderAuth(
            {"Authorization": f"OAuth {oauth_token}", "X-Org-Id": organization_id}
        )
        session = Session("https://api.tracker.yandex.net/v3", client=httpx.Client(auth=auth))
        self.me = MeClient(session)
        self.priorities = PrioritiesClient(session)

    @classmethod
    def from_env(cls) -> TrackerClient:
        """The single sanctioned env-read point (composition root); components never read env."""
        return cls(
            oauth_token=os.environ["YANDEX_ID_OAUTH_TOKEN"],
            organization_id=os.environ["YANDEX_ID_ORGANIZATION_ID"],
        )
