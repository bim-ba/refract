"""Declarative GitHub users client - transport ONLY (thin sugar over request builders)."""

from ycli.yandex.github.base import GithubResource

from . import _requests
from .models import User


class UsersClient(GithubResource):
    """Declarative HTTP for ``/user`` and ``/users/{username}``."""

    def me(self) -> User:
        """``GET /user`` → the authenticated ``User`` (a safe auth probe)."""
        return self._session.send(_requests.me())

    def get(self, username: str) -> User:
        """``GET /users/{username}`` → that user's public profile.

        Example:
            >>> client = GithubClient(github_token="…")  # doctest: +SKIP
            >>> client.users.get("octocat").login  # doctest: +SKIP
            'octocat'
        """
        return self._session.send(_requests.get(username))
