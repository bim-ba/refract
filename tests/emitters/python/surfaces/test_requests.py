from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _emit(res):
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.format import RuffFormatter
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.requests import RequestsSurface
    from refract.emitters.python.types import PythonTypeMapper

    surface = RequestsSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )
    return RuffFormatter().format(surface.emit(res, CTX))


def test_me_requests(me_resource):
    out = _emit(me_resource)
    assert "def get() -> Request[Me]:" in out
    assert 'return Request(method="GET", path="myself", response_model=Me)' in out
    assert "from ycli.yandex.tracker.runtime import Request" in out
    assert "from .models import Me" in out


def test_priorities_requests(priorities_resource):
    out = _emit(priorities_resource)
    assert "def list_() -> Request[PriorityList]:" in out  # module-level shadow guard
    assert "def create(body: PriorityCreate) -> Request[Priority]:" in out
    # edit's signature is >100 cols -> ruff hug-wraps it; assert the wrapped params line, not a
    # contiguous single-line `def edit(...)` (which ruff splits onto its own lines).
    assert "def edit(" in out
    assert "priority_id: str, body: PriorityUpdate, *, version: int | None = None" in out
    # write path renders model_dump flags straight off the ir.Body value object (by_alias/omit_none)
    assert "json_body=body.model_dump(by_alias=True, exclude_none=True)" in out
    assert 'path=f"priorities/{priority_id}"' in out
    assert 'query={"version": version}' in out
