"""GitHub repos FastMCP tools (reads + one write, honest safety annotations)."""

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from ycli.yandex.github.client import GithubClient
from ycli.yandex.github.dependencies import RO, TAGS, WRITE, WRITE_TAGS, github_client
from ycli.yandex.github.repos.models import Issue, IssueCreate, IssueList, Repo

mcp = FastMCP("github-repos")


@mcp.tool(name="repos_get", annotations={**RO, "title": "Get a GitHub repository"}, tags=TAGS)
def get(owner: str, repo: str, client: GithubClient = Depends(github_client)) -> Repo:
    """One repository's metadata, by owner and name."""
    return client.repos.get(owner, repo)


@mcp.tool(
    name="repos_issues_list",
    annotations={**RO, "title": "List GitHub repository issues"},
    tags=TAGS,
)
def issues(
    owner: str,
    repo: str,
    state: str | None = None,
    per_page: int | None = None,
    client: GithubClient = Depends(github_client),
) -> IssueList:
    """Issues of one repository; pull requests are included by the API."""
    return client.repos.issues(owner, repo, state=state, per_page=per_page)


@mcp.tool(
    name="repos_issues_create",
    annotations={**WRITE, "title": "Open a GitHub issue"},
    tags=WRITE_TAGS,
)
def create_issue(
    owner: str, repo: str, body: IssueCreate, client: GithubClient = Depends(github_client)
) -> Issue:
    """Open an issue in a repository.

    CAUTION: an issue is public in a public repository and notifies every watcher; the API
    offers no delete, so a created issue can only be closed. Confirm ``owner``/``repo`` before
    calling.
    """
    return client.repos.create_issue(owner, repo, body)
