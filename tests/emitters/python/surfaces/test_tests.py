from refract import ir
from refract.emitters.api import EmitContext

# _URL now builds from ctx.config.server.base_url (base_url moved off Resource to ClientConfig).
CTX = EmitContext(
    package_root="ycli.yandex.tracker",
    config=ir.ClientConfig(
        name="tracker",
        server=ir.Server(base_url="https://api.tracker.yandex.net/v3"),
    ),
)


def _surface():
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.tests import TestsSurface
    from refract.emitters.python.types import PythonTypeMapper

    return TestsSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )


def _emit(res):
    from refract.emitters.python.format import RuffFormatter

    return RuffFormatter().format(_surface().emit(res, CTX))


def test_tests_applies_only_when_cases_exist(me_resource, priorities_resource):
    assert _surface().applies(me_resource) is True
    assert _surface().applies(priorities_resource) is False   # priorities carries no test cases


def test_me_tests(me_resource):
    out = _emit(me_resource)
    assert '"""Tracker /myself resource - client + CLI + MCP, HTTP stubbed."""' in out
    assert "from __future__ import annotations" in out
    assert "import asyncio" in out
    assert "import json" in out
    assert "import pytest" in out
    assert "import responses" in out
    assert "from fastmcp import Client" in out
    assert "from fastmcp.exceptions import ToolError" in out
    assert "from typer.testing import CliRunner" in out
    assert "import ycli.cli.app as cli" in out
    assert "from ycli.mcp import mcp as root_mcp" in out
    assert "from ycli.yandex.tracker.client import TrackerClient" in out
    assert "from ycli.yandex.tracker.me import mcp as me_mcp_module" in out
    assert "from ycli.yandex.tracker.me.models import Me" in out
    assert '_URL = "https://api.tracker.yandex.net/v3/myself"' in out
    assert (
        '_PAYLOAD = {"uid": 42, "login": "alice", "display": "Alice A.", '
        '"email": "alice@example.com"}'
    ) in out
    assert "_runner = CliRunner()" in out
    assert "@responses.activate" in out
    assert "def test_me_client_get(creds):" in out
    assert "responses.add(responses.GET, _URL, json=_PAYLOAD, status=200)" in out
    assert "me = TrackerClient(oauth_token=\"t\", organization_id=\"o\").me.get()" in out
    assert "assert isinstance(me, Me)" in out
    assert 'res = _runner.invoke(cli.app, ["--format", "json", "tracker", "me", "get"])' in out
    assert 'return await client.call_tool("tracker_me_get", {})' in out
    assert "async def test_me_mcp_auth_guard(creds):" in out
    assert "responses.add(responses.GET, _URL, json={}, status=401)" in out
    assert "async with Client(me_mcp_module.mcp) as client:" in out
    assert "with pytest.raises(ToolError):" in out
    assert '            await client.call_tool("me_get", {})' in out
    assert (
        '"""200 with empty body hits the login-is-None guard '
        '(e.g. bad permissions -> blank object)."""'
    ) in out
