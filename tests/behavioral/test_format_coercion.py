"""L3 proof for Task 8: an `int64`-formatted scalar field lowers to `Annotated[int,
BeforeValidator(coerce_int64)]`, and pydantic actually runs the coercer on real JSON.

A tiny one-field model goes through the REAL entry point (`SpecLoader.load` from a YAML file, not
`_field`/`ir.Field` directly), then the real `ModelsSurface` + `RuffFormatter` render an importable
models module. The shared base module stub hand-writes `coerce_int64` (mirroring the existing
hand-written `APIModel`/`require_found` convention) - refract emits only the `Annotated[...,
BeforeValidator(...)]` wiring, never the coercion logic itself.
"""

import importlib
import sys

import pytest

from refract.emitters.api import EmitContext
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.environment import make_environment
from refract.emitters.python.format import RuffFormatter
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.surfaces.models import ModelsSurface
from refract.emitters.python.types import PythonTypeMapper
from refract.spec.loader import SpecLoader

pytestmark = pytest.mark.behavioral

_RESOURCE_YAML = """
domain: demo
resource: widgets
security: tok
models:
  - name: Widget
    fields:
      - {name: cores, type: integer, format: int64}
operations:
  - name: get
    method: GET
    path: widgets
    operationId: widgets_get
    responses:
      200: {model: Widget}
    mcp:
      name: widgets_get
      safety: RO
      title: Get
      documentation: Get a widget.
"""


def _write_models_module(tmp_path):
    """Generate `widgetpkg/demo/models.py` from the spec above + a shared-base stub (APIModel +
    a HAND-WRITTEN coerce_int64 - the exact convention Task 8's wiring assumes)."""
    resource_yaml = tmp_path / "resource.yaml"
    resource_yaml.write_text(_RESOURCE_YAML, encoding="utf-8")
    res = SpecLoader.load(resource_yaml)

    parts = (PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment())
    ctx = EmitContext(package_root="widgetpkg.demo")
    source = RuffFormatter().format(ModelsSurface(*parts).emit(res, ctx))

    pkg = tmp_path / "widgetpkg"
    (pkg / "demo").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    # Shared base module: models.jinja always imports APIModel + any coercer from one level above
    # package_root (D2/G2 convention). coerce_int64 is HAND-WRITTEN here - refract never generates
    # coercion logic, only the Annotated[..., BeforeValidator(...)] call site.
    (pkg / "models.py").write_text(
        "from pydantic import BaseModel\n\n\n"
        "class APIModel(BaseModel):\n    pass\n\n\n"
        "def coerce_int64(value):\n"
        "    return int(value)\n",
        encoding="utf-8",
    )
    (pkg / "demo" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "demo" / "models.py").write_text(source, encoding="utf-8")
    return source


def test_generated_int64_field_coerces_a_json_string_to_a_python_int(tmp_path, monkeypatch):
    """The spec above never types `cores` as anything but a plain `integer` + `format: int64` -
    yet the generated source wraps it in `Annotated[int, BeforeValidator(coerce_int64)]`, and
    pydantic actually runs the hand-written coercer: a JSON STRING becomes a Python `int`."""
    source = _write_models_module(tmp_path)
    assert "cores: Annotated[int, BeforeValidator(coerce_int64)]" in source
    assert "from widgetpkg.models import APIModel, coerce_int64" in source

    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        models = importlib.import_module("widgetpkg.demo.models")
        widget = models.Widget.model_validate({"cores": "123"})
        assert widget.cores == 123
        assert isinstance(widget.cores, int)
    finally:
        for name in ("widgetpkg.demo.models", "widgetpkg.demo", "widgetpkg.models", "widgetpkg"):
            sys.modules.pop(name, None)
