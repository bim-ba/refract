from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _emit(res):
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.format import RuffFormatter
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.models import ModelsSurface
    from refract.emitters.python.types import PythonTypeMapper

    surface = ModelsSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )
    return RuffFormatter().format(surface.emit(res, CTX))


def test_models_applies_gates_on_models(me_resource):
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.models import ModelsSurface
    from refract.emitters.python.types import PythonTypeMapper

    surface = ModelsSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment()
    )
    assert surface.applies(me_resource) is True


def test_me_models(me_resource):
    out = _emit(me_resource)
    assert '"""Pydantic model for Tracker /myself (Me)."""' in out
    assert "from __future__ import annotations" in out
    assert "from ycli.yandex.models import APIModel" in out
    assert "class Me(APIModel):" in out
    assert (
        '"""The authenticated Tracker user (``GET /v3/myself``) — a safe auth probe."""'
        in out
    )
    assert "uid: int | None = None" in out  # NeutralType lowered via TypeMapper
    assert "login: str | None = None" in out
    assert "from pydantic import" not in out  # me needs neither Field nor RootModel


def test_priorities_models(priorities_resource):
    out = _emit(priorities_resource)
    assert "from pydantic import Field, RootModel" in out
    assert "class PriorityList(RootModel[list[Priority]]):" in out  # RootListModel case
    assert "class Priority(APIModel):" in out
    assert 'key: str = Field(description="Key of the new priority.")' in out  # required
    assert (
        'name: LocalizedName = Field(description="Localized display name of the priority.")'
        in out
    )  # ref type
    assert (
        'ru: str | None = Field(default=None, description="Name in Russian.")' in out
    )  # optional + described
