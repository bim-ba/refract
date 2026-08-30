"""Request builders for Github repos - the single HTTP contract (sans-I/O)."""

from ycli.yandex.github.runtime import Request

from .models import Issue, IssueCreate, IssueList, Repo


def get(owner: str, repo: str) -> Request[Repo]:
    """``GET /repos/{owner}/{repo}`` -> Repo request builder."""
    return Request(method="GET", path=f"repos/{owner}/{repo}", response_model=Repo)


def issues(
    owner: str, repo: str, *, state: str | None = None, per_page: int | None = None
) -> Request[IssueList]:
    """``GET /repos/{owner}/{repo}/issues`` -> IssueList request builder."""
    return Request(
        method="GET",
        path=f"repos/{owner}/{repo}/issues",
        query={"state": state, "per_page": per_page},
        response_model=IssueList,
    )


def create_issue(owner: str, repo: str, body: IssueCreate) -> Request[Issue]:
    """``POST /repos/{owner}/{repo}/issues`` - create_issue request from a typed body."""
    return Request(
        method="POST",
        path=f"repos/{owner}/{repo}/issues",
        json_body=body.model_dump(by_alias=True, exclude_none=True),
        response_model=Issue,
    )
