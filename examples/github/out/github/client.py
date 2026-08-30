"""Github client - the composition root (aggregates resources, owns transport + auth)."""

from __future__ import annotations

import os

import httpx

from .repos.client import ReposClient
from .runtime.auth import HeaderAuth
from .runtime.session import Session
from .users.client import UsersClient


class GithubClient:
    """Root client for the Github API."""

    def __init__(self, *, github_token: str) -> None:
        auth = HeaderAuth("Authorization", f"Bearer {github_token}")
        session = Session("https://api.github.com", client=httpx.Client(auth=auth))
        self.repos = ReposClient(session)
        self.users = UsersClient(session)

    @classmethod
    def from_env(cls) -> GithubClient:
        """The single sanctioned env-read point (composition root); components never read env."""
        return cls(
            github_token=os.environ["GITHUB_TOKEN"],
        )
