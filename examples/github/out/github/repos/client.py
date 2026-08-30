"""Declarative GitHub repos client - transport ONLY (thin sugar over request builders)."""

from ycli.yandex.github.base import GithubResource

from . import _requests
from .models import Issue, IssueCreate, IssueList, Repo


class ReposClient(GithubResource):
    """Declarative HTTP for ``/repos/{owner}/{repo}`` (repository + issues)."""

    def get(self, owner: str, repo: str) -> Repo:
        """``GET /repos/{owner}/{repo}`` → one repository.

        Example:
            >>> client = GithubClient(github_token="…")  # doctest: +SKIP
            >>> client.repos.get("octocat", "Hello-World").full_name  # doctest: +SKIP
            'octocat/Hello-World'
        """
        return self._session.send(_requests.get(owner, repo))

    def issues(
        self, owner: str, repo: str, *, state: str | None = None, per_page: int | None = None
    ) -> IssueList:
        """``GET /repos/{owner}/{repo}/issues`` → the repository's issues.

        GitHub returns pull requests through this endpoint too; ``state`` defaults to ``open``.

        Example:
            >>> client = GithubClient(github_token="…")  # doctest: +SKIP
            >>> client.repos.issues("octocat", "Hello-World", state="all").root[
            ...     0
            ... ].number  # doctest: +SKIP
            11054
        """
        return self._session.send(_requests.issues(owner, repo, state=state, per_page=per_page))

    def create_issue(self, owner: str, repo: str, body: IssueCreate) -> Issue:
        """Open an issue in ``owner/repo`` from a typed ``IssueCreate`` body. Returns the new ``Issue``.

        Example:
            >>> client = GithubClient(github_token="…")  # doctest: +SKIP
            >>> client.repos.create_issue(
            ...     "octocat", "Hello-World", IssueCreate(title="Bug")
            ... ).number  # doctest: +SKIP
            11054
        """
        return self._session.send(_requests.create_issue(owner, repo, body))
