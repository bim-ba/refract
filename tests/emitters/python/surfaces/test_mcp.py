from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _surface():
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.mcp import McpSurface
    from refract.emitters.python.types import PythonTypeMapper

    return McpSurface(PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment())


def _emit(res):
    from refract.emitters.python.format import RuffFormatter

    return RuffFormatter().format(_surface().emit(res, CTX))


def test_mcp_applies_on_mcp_facet(me_resource):
    assert _surface().applies(me_resource) is True


def test_me_mcp(me_resource):
    out = _emit(me_resource)
    assert '"""Tracker /myself FastMCP tool (reads-only) — Depends DI."""' in out
    assert "from fastmcp import FastMCP" in out
    assert "from fastmcp.dependencies import Depends" in out
    assert "from ycli.yandex.models import require_found" in out  # shared-base guard import
    assert "from ycli.yandex.tracker.client import TrackerClient" in out  # package_root-derived
    assert "from ycli.yandex.tracker.dependencies import RO, TAGS, tracker_client" in out
    assert "from ycli.yandex.tracker.me.models import Me" in out
    assert 'mcp = FastMCP("tracker-me")' in out
    decorator = (
        '@mcp.tool(name="me_get", annotations={**RO, "title": "Get current Tracker user"}, '
        "tags=TAGS)"
    )
    assert decorator in out
    assert "def get(client: TrackerClient = Depends(tracker_client)) -> Me:" in out
    assert "result = client.me.get()" in out
    assert "require_found(" in out
    assert "sentinel=lambda r: r.login is None," in out


def test_priorities_mcp(priorities_resource):
    out = _emit(priorities_resource)
    assert 'mcp = FastMCP("tracker-priorities")' in out
    assert (
        "def list_(client: TrackerClient = Depends(tracker_client)) -> PriorityList:" in out
    )  # shadow guard
    assert "return client.priorities.list()" in out
    assert 'annotations={**WRITE, "title": "Create Tracker priority"}' in out
    assert "tags=WRITE_TAGS," in out
    assert 'annotations={**WRITE_IDEMPOTENT, "title": "Edit Tracker priority"}' in out
    assert "def edit(" in out
    assert "priority_id: str," in out
    assert "body: PriorityUpdate," in out
    assert "version: int | None = None," in out  # query param via TypeMapper
    assert "client: TrackerClient = Depends(tracker_client)," in out
    assert "return client.priorities.edit(priority_id, body, version=version)" in out
    assert "require_found" not in out  # priorities declares no guard
