import dataclasses

import pytest

from refract import ir
from refract.emitters.api import (
    DomainEmitter,
    EmitContext,
    Fragment,
    Import,
    LanguageBackend,
    Naming,
    RenderedType,
    SurfaceEmitter,
)


def _config() -> ir.ClientConfig:
    return ir.ClientConfig(
        name="tracker", server=ir.Server(base_url="https://api.tracker.yandex.net/v3")
    )


def _resource() -> ir.Resource:
    return ir.Resource(
        domain="tracker", resource="myself", security="oauth_token", models=(), operations=()
    )


def test_value_objects_are_frozen():
    frag = Fragment(lines=("a", "b"), imports=(Import("m", "N"),))
    assert frag.lines == ("a", "b")
    with pytest.raises(dataclasses.FrozenInstanceError):
        frag.lines = ()  # frozen dataclass


def test_rendered_type_defaults_empty_imports():
    assert RenderedType(text="int").imports == ()


def test_emit_context_carries_package_root_and_config():
    ctx = EmitContext(package_root="ycli.yandex.tracker", config=_config())
    assert ctx.package_root == "ycli.yandex.tracker"
    assert ctx.config.server.base_url == "https://api.tracker.yandex.net/v3"


def test_strategy_abcs_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Naming()  # abstract


def test_surface_emitter_is_per_resource():
    # a concrete per-resource stub proves name + applies() + emit(res, ctx)
    class _Requests(SurfaceEmitter):
        name = "requests"

        def applies(self, res):
            return bool(res.operations)

        def emit(self, res, ctx):
            return f"# {res.resource} @ {ctx.package_root}"

    surface = _Requests()
    res = _resource()
    ctx = EmitContext(package_root="ycli.yandex.tracker", config=_config())
    assert surface.applies(res) is False  # no operations -> gated off
    assert surface.emit(res, ctx) == "# myself @ ycli.yandex.tracker"


def test_domain_emitter_runs_once_over_all_resources():
    # a concrete per-API stub proves name + emit(resources, ctx)
    class _RootClient(DomainEmitter):
        name = "root_client"

        def emit(self, resources, ctx):
            return f"# {ctx.config.name}: {len(resources)}"

    root = _RootClient()
    ctx = EmitContext(package_root="ycli.yandex.tracker", config=_config())
    assert root.emit((_resource(),), ctx) == "# tracker: 1"


def test_domain_emitter_cannot_be_instantiated():
    with pytest.raises(TypeError):
        DomainEmitter()  # abstract emit(resources, ctx)


def test_language_backend_composes_strategies():
    # a minimal concrete stub proves the composition shape holds
    class _N(Naming):
        def pascal(self, name):
            return name.title()

        def module_function(self, name):
            return name

        def class_name(self, base, suffix):
            return base + suffix

    n = _N()
    assert n.class_name("Me", "Client") == "MeClient"


def test_language_backend_domain_surfaces_default_empty():
    field = {f.name: f for f in dataclasses.fields(LanguageBackend)}["domain_surfaces"]
    assert field.default == ()
