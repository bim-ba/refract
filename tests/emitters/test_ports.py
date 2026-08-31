import dataclasses

import pytest

from refract import ir
from refract.emitters.ports import (
    DomainEmitter,
    EmitContext,
    LanguageBackend,
    Naming,
    RenderedType,
    SurfaceEmitter,
)
from refract.emitters.python.backend import python_backend


def _config() -> ir.ClientConfig:
    return ir.ClientConfig(
        name="tracker", server=ir.Server(base_url="https://api.tracker.yandex.net/v3")
    )


def _resource() -> ir.Resource:
    return ir.Resource(
        domain="tracker", resource="myself", security="oauth_token", models=(), operations=()
    )


def _ctx() -> EmitContext:
    """A context built the one sanctioned way - off a backend, so it carries that backend's own
    strategies (`LanguageBackend.context`)."""
    return python_backend().context("ycli.yandex.tracker", _config())


def test_value_objects_are_frozen():
    rt = RenderedType(text="x")
    with pytest.raises(dataclasses.FrozenInstanceError):
        rt.text = "y"  # ty: ignore[invalid-assignment]  # frozen dataclass


def test_rendered_type_defaults_empty_imports():
    assert RenderedType(text="int").imports == ()


def test_backend_context_carries_package_root_config_and_strategies():
    """`LanguageBackend.context` is the ONE constructor: it pairs the caller's per-generation
    values with the backend's own strategies, so a resolver can never read a strategy from a
    backend other than the one whose templates render its page."""
    backend = python_backend()
    ctx = backend.context("ycli.yandex.tracker", _config())
    assert ctx.package_root == "ycli.yandex.tracker"
    assert ctx.config is not None  # narrow ClientConfig | None before attribute access
    assert ctx.config.server.base_url == "https://api.tracker.yandex.net/v3"
    assert ctx.naming is backend.naming
    assert ctx.type_mapper is backend.type_mapper
    assert ctx.doc_comments is backend.doc_comments


def test_backend_context_defaults_config_to_none():
    """A per-resource surface (requests/client/models/cli/mcp/package) never reads `config`, so
    the argument is optional - only tests (base_url) and root_client require it."""
    assert python_backend().context("ycli.yandex.tracker").config is None


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
    ctx = _ctx()
    assert surface.applies(res) is False  # no operations -> gated off
    assert surface.emit(res, ctx) == "# myself @ ycli.yandex.tracker"


def test_domain_emitter_runs_once_over_all_resources():
    # a concrete per-API stub proves name + emit(resources, ctx)
    class _RootClient(DomainEmitter):
        name = "root_client"

        def emit(self, resources, ctx):
            return f"# {ctx.config.name}: {len(resources)}"

    root = _RootClient()
    ctx = _ctx()
    assert root.emit((_resource(),), ctx) == "# tracker: 1"


def test_domain_emitter_applies_defaults_to_true():
    """The published default: a DomainEmitter that declares no gate always applies. Every surface
    in the Python table states its own gate, so this arm is reachable only through the ABC - which
    is exactly the contract a new backend implements (docs/adding-a-language.md)."""

    class _AlwaysOn(DomainEmitter):
        name = "root_client"

        def emit(self, resources, ctx):
            return ""

    assert _AlwaysOn().applies((_resource(),)) is True


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

        def safe_param(self, name):
            return name

        def class_name(self, base, suffix):
            return base + suffix

        def cli_option(self, *parts):
            return "_".join(parts)

    n = _N()
    assert n.class_name("Me", "Client") == "MeClient"


def test_language_backend_domain_surfaces_default_empty():
    field = {f.name: f for f in dataclasses.fields(LanguageBackend)}["domain_surfaces"]
    assert field.default == ()
