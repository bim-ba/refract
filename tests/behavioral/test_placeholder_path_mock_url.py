"""L3 proof for issue #17: a generated test for a `{placeholder}` path must stub the URL its own
client call actually requests.

`_URL_<op>` used to be `base_url + op.path` verbatim, so an operation on `widgets/{id}` stubbed
`https://api.demo/v1/widgets/{id}` - braces and all - while the client requested
`https://api.demo/v1/widgets/W-1`. No corpus operation had both a placeholder path and a `tests:`
facet, so nothing ever fired.

This runs the REAL pipeline end to end (mirrors `test_nested_ref_test_imports.py`): the IR below
goes through the real Requests/Client/RootClient/Tests surfaces + `RuffFormatter`, is written into
an importable package, and the generated CLIENT test is `ast.parse`d, imported and INVOKED against
a fake `responses` module that - unlike the one next door - asserts the requested URL EQUALS the
registered stub URL. `{id}` is deliberately a shadowed name (`id_` in the emitted signature), so
the deconflict path is exercised on both sides at once.
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

pytestmark = pytest.mark.behavioral

_WIDGET = ir.ObjectModel(
    name="Widget", fields=(ir.Field(name="name", type=ir.ScalarType(scalar="string")),)
)

_GET_CASE = ir.TestCase(
    name="widgets_client_get",
    kind=ir.TestKind.CLIENT,
    http_method="GET",
    path_args=(("id", "W-1"),),  # the value the client below sends for `widgets/{id}`
    status=200,
    response_json={"name": "ok"},
    has_json=True,
    asserts=("widgets.name == 'ok'",),
    call="DemoClient(token='x').widgets.get('W-1')",
)

_RESOURCE = ir.Resource(
    domain="demo",
    resource="widgets",
    security="token",
    models=(_WIDGET,),
    operations=(
        ir.Operation(
            name="get",
            method="GET",
            path="widgets/{id}",  # `id` shadows a builtin -> `id_` in the emitted signature
            operation_id="widgets_get",
            params=(ir.Param(name="id", loc="path", type=ir.ScalarType(scalar="string")),),
            response_model="Widget",
            tests=(_GET_CASE,),
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

_URL_ASSERTING_RESPONSES_MODULE = '''
"""A minimal stand-in for the `responses` library (a downstream-only dev dependency) that asserts
the REQUESTED url against the REGISTERED one - the whole point of issue #17."""

import functools

GET = "GET"


def add(method, url, json=None, status=200):
    global _stub
    _stub = {"method": method, "url": url, "json": json, "status": status}


def activate(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        import httpx

        original_request = httpx.Client.request

        def fake_request(self, method, url, **kw):
            assert method == _stub["method"]
            assert str(url) == _stub["url"], f"requested {url!r}, stubbed {_stub['url']!r}"
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

_MODULES = (
    "test_widgets_generated",
    "responses",
    "demopkg.client",
    "demopkg.widgets.client",
    "demopkg.widgets._requests",
    "demopkg.widgets.models",
    "demopkg.widgets",
    "demopkg.runtime.session",
    "demopkg.runtime.auth",
    "demopkg.runtime",
    "demopkg.base",
    "demopkg",
)


def _write_pkg(tmp_path):
    """Generate `demopkg/{models,_requests,client}.py` + the root client, plus the runtime shims
    bridging refract's reference runtime (mirrors `test_nested_ref_test_imports.py`)."""
    parts = (PythonNaming(), PythonTypeMapper(), PythonDocComments(), make_template_environment())
    fmt = RuffFormatter()
    ctx = EmitContext(package_root="demopkg", config=_CONFIG)

    pkg = tmp_path / "demopkg"
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
        "class Widget(BaseModel):\n    name: str | None = None\n",
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


def test_generated_test_stubs_the_url_the_generated_client_requests(tmp_path, monkeypatch):
    """The issue #17 proof: the emitted `_URL_get` carries the SUBSTITUTED path, and the emitted
    test - actually invoked - reaches a request whose URL equals the one it stubbed."""
    from refract.emitters.python.surfaces.tests import TestsSurface  # local: avoid pytest
    # collecting `TestsSurface` as a `Test*`-named class (it has an `__init__`) - matches the
    # existing behavioral/surfaces test convention.

    pkg, ctx, parts = _write_pkg(tmp_path)
    naming, type_mapper, doc_comments, env = parts
    source = RuffFormatter().format(
        TestsSurface(naming, type_mapper, doc_comments, env).emit(_RESOURCE, ctx)
    )

    # (a) the mocked URL is substituted, not brace-bearing
    url_line = next(line for line in source.splitlines() if line.startswith("_URL_get"))
    assert url_line == '_URL_get = "https://api.demo/v1/widgets/W-1"'  # no brace, either spelling
    # (b) the client's request builder resolves the SAME path from the shadow-guarded param
    assert 'path=f"widgets/{id_}"' in (pkg / "widgets" / "_requests.py").read_text(encoding="utf-8")

    ast.parse(source)  # syntactically valid Python

    (tmp_path / "responses.py").write_text(_URL_ASSERTING_RESPONSES_MODULE, encoding="utf-8")
    (tmp_path / "test_widgets_generated.py").write_text(source, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        test_mod = importlib.import_module("test_widgets_generated")
        # (c) the generated test, invoked for real: the fake `responses` asserts requested==stubbed
        test_mod.test_widgets_client_get(creds=None)
    finally:
        for name in _MODULES:
            sys.modules.pop(name, None)
