"""Pydantic model for the GitHub users API (User)."""

from __future__ import annotations

from pydantic import Field
from ycli.yandex.models import APIModel


class User(APIModel):
    """A GitHub user account (``GET /user``, ``GET /users/{username}``).

    Example:
        >>> User.model_validate({"login": "octocat", "id": 583231}).login
        'octocat'
    """

    login: str | None = Field(default=None, description="The user's handle.")
    id: int | None = Field(default=None, description="Numeric account id.")
    name: str | None = Field(default=None, description="Display name (null when unset).")
    company: str | None = Field(default=None, description="Company (null when unset).")
    location: str | None = Field(default=None, description="Location (null when unset).")
    html_url: str | None = Field(default=None, description="The profile page on github.com.")
    public_repos: int | None = Field(default=None, description="Count of public repositories.")
    followers: int | None = Field(default=None, description="Count of followers.")
    created_at: str | None = Field(
        default=None, description="Account creation timestamp (ISO 8601)."
    )
