"""GitHub users FastMCP tools (reads-only) — Depends DI."""

from fastmcp import FastMCP
from fastmcp.dependencies import Depends
from ycli.yandex.github.client import GithubClient
from ycli.yandex.github.dependencies import RO, TAGS, github_client
from ycli.yandex.github.users.models import User
from ycli.yandex.models import require_found

mcp = FastMCP("github-users")


@mcp.tool(
    name="users_me", annotations={**RO, "title": "Get the authenticated GitHub user"}, tags=TAGS
)
def me(client: GithubClient = Depends(github_client)) -> User:
    """The user the GITHUB_TOKEN belongs to (a safe auth probe)."""
    result = client.users.me()
    return require_found(
        result,
        sentinel=lambda r: r.login is None,
        message="auth probe failed — empty user (check GITHUB_TOKEN)",
    )


@mcp.tool(name="users_get", annotations={**RO, "title": "Get a GitHub user"}, tags=TAGS)
def get(username: str, client: GithubClient = Depends(github_client)) -> User:
    """The public profile of one GitHub user, by handle."""
    return client.users.get(username)
