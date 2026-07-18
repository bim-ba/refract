from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _emit(res):
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.format import RuffFormatter
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.client import ClientSurface
    from refract.emitters.python.types import PythonTypeMapper

    surface = ClientSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )
    return RuffFormatter().format(surface.emit(res, CTX))


def test_me_client(me_resource):
    out = _emit(me_resource)
    assert "class MeClient(TrackerResource):" in out
    assert "def get(self) -> Me:" in out
    assert "return self._session.send(_requests.get())" in out
    assert "from . import _requests" in out
    assert "from ycli.yandex.tracker.base import TrackerResource" in out
    # thin sugar only - no uplink decorators, no private _verb split
    assert "@uplink" not in out


def test_priorities_client(priorities_resource):
    out = _emit(priorities_resource)
    assert "class PrioritiesClient(TrackerResource):" in out
    # method name is verbatim (`list`), the builder call uses the shadow-guarded `list_`
    assert "def list(self) -> PriorityList:" in out
    assert "return self._session.send(_requests.list_())" in out
    # write op: `body: <model>` positional, call passes `body` through unchanged
    assert "def create(self, body: PriorityCreate) -> Priority:" in out
    assert "return self._session.send(_requests.create(body))" in out
    # edit: path positional + typed body + keyword-only query; ruff hug-wraps the >100-col def
    assert "def edit(" in out
    assert "self, priority_id: str, body: PriorityUpdate, *, version: int | None = None" in out
    assert "return self._session.send(_requests.edit(priority_id, body, version=version))" in out
    assert "from . import _requests" in out
    # F2: the uplink `_verb`/`verb` split is gone entirely
    assert "@uplink" not in out
    assert "def _create" not in out
    assert "def _edit" not in out
