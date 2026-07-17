import importlib
import subprocess
import sys

import httpx
import pytest

from refract import ir
from refract.emitters.api import EmitContext
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.environment import make_environment
from refract.emitters.python.format import RuffFormatter
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.surfaces.client import ClientSurface
from refract.emitters.python.surfaces.requests import RequestsSurface
from refract.emitters.python.surfaces.root_client import RootClientSurface
from refract.emitters.python.types import PythonTypeMapper
from refract.ir.types import ScalarType

pytestmark = pytest.mark.behavioral

_WIDGET = ir.Resource(
    domain="demo", resource="widget", security="token",
    models=(
        ir.ObjectModel(name="Widget", fields=(
            ir.Field(name="id", type=ScalarType(scalar="integer")),
            ir.Field(name="name", type=ScalarType(scalar="string")))),
        ir.ObjectModel(name="WidgetCreate", fields=(
            ir.Field(name="name", type=ScalarType(scalar="string")),)),
    ),
    operations=(
        ir.Operation(name="get", method="GET", path="widget", operation_id="widget_get",
                     response_model="Widget"),
        ir.Operation(name="create", method="POST", path="widget", operation_id="widget_create",
                     body=ir.Body(mode="typed_model", model="WidgetCreate"),  # by_alias/omit_none
                     response_model="Widget"),
    ),
)

# base_url + auth are per-API glue now: they live on ClientConfig, NOT on Resource.
_CONFIG = ir.ClientConfig(
    name="demo",
    server=ir.Server(base_url="https://api.demo/v1"),
    auth=(("token", ir.HeaderAuth(
        header="Authorization", template="Bearer {token}",
        inputs=(ir.AuthInput(name="token", env="DEMO_TOKEN"),))),),
)


def _write_pkg(tmp_path):
    parts = (PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment())
    fmt = RuffFormatter()
    ctx = EmitContext(package_root="demopkg", config=_CONFIG)

    pkg = tmp_path / "demopkg"
    (pkg / "widget").mkdir(parents=True)
    (pkg / "runtime").mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "widget" / "__init__.py").write_text("", encoding="utf-8")
    # runtime/base shims bridge refract's reference runtime into the ycli-flat layout (G2)
    (pkg / "runtime" / "__init__.py").write_text(
        "from refract.runtime.request import Request\n", encoding="utf-8")
    (pkg / "runtime" / "session.py").write_text(
        "from refract.runtime.session import Session\n", encoding="utf-8")
    (pkg / "runtime" / "auth.py").write_text(
        "from refract.runtime.auth import HeaderAuth, MultiHeaderAuth\n", encoding="utf-8")
    (pkg / "base.py").write_text(
        "from refract.runtime.base import Resource as DemoResource\n", encoding="utf-8")
    (pkg / "widget" / "models.py").write_text(
        "from pydantic import BaseModel\n\n\n"
        "class Widget(BaseModel):\n    id: int | None = None\n    name: str | None = None\n\n\n"
        "class WidgetCreate(BaseModel):\n    name: str\n", encoding="utf-8")

    (pkg / "widget" / "_requests.py").write_text(
        fmt.format(RequestsSurface(*parts).emit(_WIDGET, ctx)), encoding="utf-8")
    (pkg / "widget" / "client.py").write_text(
        fmt.format(ClientSurface(*parts).emit(_WIDGET, ctx)), encoding="utf-8")
    (pkg / "client.py").write_text(  # root-client glue: DomainEmitter runs over the resource tuple
        fmt.format(RootClientSurface(*parts).emit((_WIDGET,), ctx)), encoding="utf-8")
    return pkg


def test_generated_sources_are_ruff_clean(tmp_path):
    pkg = _write_pkg(tmp_path)
    for rel in ("widget/_requests.py", "widget/client.py", "client.py"):
        r = subprocess.run(["ruff", "check", str(pkg / rel)], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr


def test_generated_root_client_imports_and_sends(tmp_path, monkeypatch):
    _write_pkg(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    # stub every httpx.Client the generated root client builds with a MockTransport; the auth the
    # root client installs (httpx.Auth on the client) must reach the transport's request.
    def handler(request):
        assert request.headers["Authorization"] == "Bearer x"  # auth-agnostic, auth on client
        return httpx.Response(200, json={"id": 1, "name": "x"})

    real_client = httpx.Client

    def stub_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", stub_client)
    try:
        # builders are pure - no I/O
        requests_mod = importlib.import_module("demopkg.widget._requests")
        from demopkg.widget.models import Widget, WidgetCreate
        assert requests_mod.get().path == "widget"
        assert requests_mod.create(WidgetCreate(name="x")).json_body == {"name": "x"}

        # the generated root client builds Session + httpx.Client(auth=HeaderAuth) from
        # ClientConfig; client.res.op(...) sugars through the auth-agnostic Session.send
        root_mod = importlib.import_module("demopkg.client")
        client = root_mod.DemoClient(token="x")
        widget = client.widget.get()
        assert isinstance(widget, Widget) and widget.id == 1
    finally:
        for name in ("demopkg.client", "demopkg.widget.client", "demopkg.widget._requests",
                     "demopkg.widget.models", "demopkg.widget", "demopkg.runtime.session",
                     "demopkg.runtime.auth", "demopkg.runtime", "demopkg.base", "demopkg"):
            sys.modules.pop(name, None)
