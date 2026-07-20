"""L3 proof for Task 11 (M1): a body model's `list<ref<Item>>` field is now imported by the
generated CLIENT test (`_body_test_imports` -> `_referenced_model_names`), so the authored `call`
that constructs `Widget(items=[Item(...)])` no longer hits a latent `NameError` - today (pre-fix)
only a DIRECT `ref<...>` body field was ever imported, one level deep.

Runs the REAL pipeline end to end: the IR resource below goes through the real
`ModelsSurface`/`RequestsSurface`/`ClientSurface`/`RootClientSurface`/`TestsSurface` + a
`RuffFormatter`, is written into an importable package, then the generated CLIENT test module is
`ast.parse`d, imported, and its test function is actually INVOKED against a tiny fake `responses`
module (a real dev dependency would be downstream-only) that intercepts `httpx.Client.request` -
proving the full round trip: no `NameError`, and the nested-ref body value survives the HTTP
stub -> Session -> pydantic parse -> asserted result.
"""

from __future__ import annotations

import ast
import importlib
import sys

import pytest

from refract import ir
from refract.emitters.ports import EmitContext
from refract.emitters.python.doc_comments import PythonDocComments
from refract.emitters.python.format import RuffFormatter
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.surfaces.client import ClientSurface
from refract.emitters.python.surfaces.requests import RequestsSurface
from refract.emitters.python.surfaces.root_client import RootClientSurface
from refract.emitters.python.templating import make_template_environment
from refract.emitters.python.types import PythonTypeMapper
from refract.ir.types import ListType, RefType

pytestmark = pytest.mark.behavioral

_ITEM = ir.ObjectModel(
    name="Item", fields=(ir.Field(name="name", type=ir.ScalarType(scalar="string")),)
)
_WIDGET = ir.ObjectModel(
    name="Widget", fields=(ir.Field(name="items", type=ListType(item=RefType(target="Item"))),)
)

_CREATE_CASE = ir.TestCase(
    name="widgets_client_create",
    kind=ir.TestKind.CLIENT,
    http_method="POST",
    path="widgets",
    status=200,
    response_json={"items": [{"name": "a"}]},
    has_json=True,
    asserts=("widgets.items[0].name == 'a'",),
    # the authored `call` literally constructs BOTH classes - Item is only reachable through
    # Widget's `list<ref<Item>>` field, never a direct ref, so pre-fix this NameErrors at runtime.
    call="DemoClient(token='x').widgets.create(Widget(items=[Item(name='a')]))",
)

_RESOURCE = ir.Resource(
    domain="demo",
    resource="widgets",
    security="token",
    models=(_WIDGET, _ITEM),
    operations=(
        ir.Operation(
            name="create",
            method="POST",
            path="widgets",
            operation_id="widgets_create",
            body=ir.Body(mode="typed_model", model="Widget"),
            response_model="Widget",
            tests=(_CREATE_CASE,),
        ),
    ),
)

_CONFIG = ir.ClientConfig(
    name="demo",
    server=ir.Server(base_url="https://api.demo/v1"),
    auth=(
        (
            "token",
            ir.HeaderAuth(
                header="Authorization",
                template="Bearer {token}",
                inputs=(ir.AuthInput(name="token", env="DEMO_TOKEN"),),
            ),
        ),
    ),
)

_FAKE_RESPONSES_MODULE = '''
"""A minimal in-process stand-in for the `responses` library (a downstream-only dev dependency):
just enough surface (GET/POST + add + activate) for a generated CLIENT test to run for real,
intercepting httpx.Client.request instead of urllib3."""

import functools

GET = "GET"
POST = "POST"

_stub = None


def add(method, url, json=None, status=200):
    global _stub
    _stub = {"method": method, "url": url, "json": json, "status": status}


def activate(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import httpx

        original_request = httpx.Client.request

        def fake_request(self, method, url, **kw):
            assert _stub is not None, "no stub registered"
            assert method == _stub["method"]
            return httpx.Response(
                _stub["status"], json=_stub["json"], request=httpx.Request(method, url)
            )

        httpx.Client.request = fake_request
        try:
            return func(*args, **kwargs)
        finally:
            httpx.Client.request = original_request

    return wrapper
'''


def _write_pkg(tmp_path):
    """Generate `nestedrefpkg/{models,_requests,client}.py` + root `client.py`, plus the
    `runtime`/`base` shims bridging refract's reference runtime (mirrors `test_d_core_runs.py`)."""
    parts = (PythonNaming(), PythonTypeMapper(), PythonDocComments(), make_template_environment())
    fmt = RuffFormatter()
    ctx = EmitContext(package_root="nestedrefpkg", config=_CONFIG)

    pkg = tmp_path / "nestedrefpkg"
    (pkg / "widgets").mkdir(parents=True)
    (pkg / "runtime").mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "widgets" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "runtime" / "__init__.py").write_text(
        "from refract.runtime.request import Request\n", encoding="utf-8"
    )
    (pkg / "runtime" / "session.py").write_text(
        "from refract.runtime.session import Session\n", encoding="utf-8"
    )
    (pkg / "runtime" / "auth.py").write_text(
        "from refract.runtime.auth import HeaderAuth, MultiHeaderAuth\n", encoding="utf-8"
    )
    (pkg / "base.py").write_text(
        "from refract.runtime.base import Resource as DemoResource\n", encoding="utf-8"
    )
    (pkg / "widgets" / "models.py").write_text(
        "from pydantic import BaseModel\n\n\n"
        "class Item(BaseModel):\n    name: str | None = None\n\n\n"
        "class Widget(BaseModel):\n    items: list[Item] | None = None\n",
        encoding="utf-8",
    )
    (pkg / "widgets" / "_requests.py").write_text(
        fmt.format(RequestsSurface(*parts).emit(_RESOURCE, ctx)), encoding="utf-8"
    )
    (pkg / "widgets" / "client.py").write_text(
        fmt.format(ClientSurface(*parts).emit(_RESOURCE, ctx)), encoding="utf-8"
    )
    (pkg / "client.py").write_text(
        fmt.format(RootClientSurface(*parts).emit((_RESOURCE,), ctx)), encoding="utf-8"
    )
    return pkg, ctx, parts


def test_generated_client_test_for_nested_list_ref_body_imports_and_runs_clean(
    tmp_path, monkeypatch
):
    """The core M1 proof: `_referenced_model_names` (walked through `_body_test_imports`) makes
    the generated test import BOTH `Widget` and `Item` - and the generated test, actually invoked,
    runs the authored `Widget(items=[Item(...)])` construction with no `NameError`."""
    from refract.emitters.python.surfaces.tests import TestsSurface  # local: avoid pytest
    # collecting `TestsSurface` as a `Test*`-named class (it has an `__init__`) - matches the
    # existing `surfaces/test_tests.py` convention.

    _pkg, ctx, parts = _write_pkg(tmp_path)
    naming, type_mapper, doc_comments, env = parts
    source = RuffFormatter().format(
        TestsSurface(naming, type_mapper, doc_comments, env).emit(_RESOURCE, ctx)
    )

    # the regression this task fixes: BOTH classes constructed in the authored `call` are
    # imported - `Item` is reachable only through Widget's `list<ref<Item>>` field, never directly.
    assert "from nestedrefpkg.widgets.models import Item, Widget" in source

    ast.parse(source)  # syntactically valid Python

    (tmp_path / "responses.py").write_text(_FAKE_RESPONSES_MODULE, encoding="utf-8")
    (tmp_path / "test_widgets_generated.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        test_mod = importlib.import_module("test_widgets_generated")
        # both classes actually bound in the test module's namespace (not just present in source)
        assert test_mod.Item is not None
        assert test_mod.Widget is not None

        try:
            test_mod.test_widgets_client_create(creds=None)  # the generated test, invoked for real
        except NameError as exc:  # pragma: no cover - only reachable pre-fix
            pytest.fail(f"generated test raised NameError (missing import): {exc}")
    finally:
        for name in (
            "test_widgets_generated",
            "responses",
            "nestedrefpkg.client",
            "nestedrefpkg.widgets.client",
            "nestedrefpkg.widgets._requests",
            "nestedrefpkg.widgets.models",
            "nestedrefpkg.widgets",
            "nestedrefpkg.runtime.session",
            "nestedrefpkg.runtime.auth",
            "nestedrefpkg.runtime",
            "nestedrefpkg.base",
            "nestedrefpkg",
        ):
            sys.modules.pop(name, None)
