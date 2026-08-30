"""Pydantic models for the GitHub repos API (Repo + Issue + IssueList + IssueCreate)."""

from __future__ import annotations

from pydantic import Field, RootModel
from ycli.yandex.models import APIModel


class Repo(APIModel):
    """A GitHub repository (``GET /repos/{owner}/{repo}``).

    Example:
        >>> Repo.model_validate({"full_name": "octocat/Hello-World"}).full_name
        'octocat/Hello-World'
    """

    id: int | None = Field(default=None, description="Numeric repository id.")
    name: str | None = Field(default=None, description="Repository name, without the owner.")
    full_name: str | None = Field(default=None, description="``owner/repo``.")
    private: bool | None = Field(default=None, description="Whether the repository is private.")
    html_url: str | None = Field(default=None, description="The repository page on github.com.")
    description: str | None = Field(
        default=None, description="Repository description (null when unset)."
    )
    language: str | None = Field(
        default=None, description="Primary language (null when undetected)."
    )
    stargazers_count: int | None = Field(default=None, description="Count of stars.")
    open_issues_count: int | None = Field(
        default=None, description="Count of open issues and pull requests."
    )
    default_branch: str | None = Field(default=None, description="Name of the default branch.")


class Issue(APIModel):
    """One issue of a repository (``/repos/{owner}/{repo}/issues``).

    Example:
        >>> Issue.model_validate({"number": 11054, "state": "open"}).number
        11054
    """

    id: int | None = Field(default=None, description="Numeric issue id.")
    number: int | None = Field(default=None, description="Issue number within the repository.")
    title: str | None = Field(default=None, description="Issue title.")
    state: str | None = Field(default=None, description="``open`` or ``closed``.")
    state_reason: str | None = Field(
        default=None, description="Why the issue reached its state (null when none)."
    )
    body: str | None = Field(default=None, description="Issue contents (null when empty).")
    html_url: str | None = Field(default=None, description="The issue page on github.com.")
    comments: int | None = Field(default=None, description="Count of comments.")
    created_at: str | None = Field(default=None, description="Creation timestamp (ISO 8601).")


class IssueList(RootModel[list[Issue]]):
    """A bare JSON array of issues.

    Example:
        >>> IssueList.model_validate([{"number": 1}]).root[0].number
        1
    """


class IssueCreate(APIModel):
    """Typed request body for ``POST /repos/{owner}/{repo}/issues`` (open an issue).

    Example:
        >>> IssueCreate(title="Bug", body="Steps…").model_dump(by_alias=True, exclude_none=True)
        {'title': 'Bug', 'body': 'Steps…'}
    """

    title: str = Field(description="Title of the new issue.")
    body: str | None = Field(default=None, description="Contents of the new issue.")
    milestone: int | None = Field(default=None, description="Number of the milestone to associate.")
