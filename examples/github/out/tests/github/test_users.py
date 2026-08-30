"""Github /user + users/{username} resource - client + CLI + MCP, HTTP stubbed."""

from __future__ import annotations

import asyncio
import json

import pytest
import responses
import ycli.cli.app as cli
from fastmcp import Client
from fastmcp.exceptions import ToolError
from typer.testing import CliRunner
from ycli.mcp import mcp as root_mcp
from ycli.yandex.github.client import GithubClient
from ycli.yandex.github.users import mcp as users_mcp_module
from ycli.yandex.github.users.models import User

_URL_me = "https://api.github.com/user"
_PAYLOAD_me = {"login": "octocat", "id": 583231, "name": "The Octocat"}
_runner = CliRunner()
_URL_get = "https://api.github.com/users/octocat"
_PAYLOAD_get = {"login": "octocat", "id": 583231, "html_url": "https://github.com/octocat"}


@responses.activate
def test_users_client_me(creds):
    responses.add(responses.GET, _URL_me, json=_PAYLOAD_me, status=200)
    users = GithubClient(github_token="t").users.me()
    assert isinstance(users, User)
    assert users.login == "octocat" and users.id == 583231


@responses.activate
def test_users_cli_me(creds):
    responses.add(responses.GET, _URL_me, json=_PAYLOAD_me, status=200)
    res = _runner.invoke(cli.app, ["--format", "json", "github", "users", "me"])
    assert res.exit_code == 0
    assert json.loads(res.stdout)["login"] == "octocat"


@responses.activate
def test_users_mcp_me(creds):
    responses.add(responses.GET, _URL_me, json=_PAYLOAD_me, status=200)

    async def go():
        async with Client(root_mcp) as client:
            return await client.call_tool("github_users_me", {})

    result = asyncio.run(go())
    assert result.data.login == "octocat"


@responses.activate
async def test_users_mcp_auth_guard(creds):
    responses.add(responses.GET, _URL_me, json={}, status=401)
    async with Client(users_mcp_module.mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("users_me", {})


@responses.activate
async def test_users_mcp_empty_response_guard(creds):
    """200 with empty body hits the login-is-None guard (e.g. bad permissions -> blank object)."""
    responses.add(responses.GET, _URL_me, json={}, status=200)
    async with Client(users_mcp_module.mcp) as client:
        with pytest.raises(ToolError):
            await client.call_tool("users_me", {})


@responses.activate
def test_users_client_get(creds):
    responses.add(responses.GET, _URL_get, json=_PAYLOAD_get, status=200)
    users = GithubClient(github_token="t").users.get("octocat")
    assert isinstance(users, User)
    assert users.html_url == "https://github.com/octocat"
