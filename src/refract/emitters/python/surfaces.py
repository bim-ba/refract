"""The Python backend's surface table.

Every surface but `package` does the same three things - gate on data presence, resolve the
resource into a page view, render that view through a jinja template - and differs only in the
four values a `SurfaceSpec` row carries. One generic emitter per arity (per-resource,
per-domain) reads those rows, so adding a surface is a new row plus its resolver and template,
not a new class.

The template FILENAME stays a table value on purpose: templates are the hand-editable seam
(open `templates/models.jinja`, read it, change it), so the table names them rather than hiding
them behind a class.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from refract.emitters.ports import DomainEmitter, EmitContext, SurfaceEmitter
from refract.emitters.python.resolve.cli import resolve_cli
from refract.emitters.python.resolve.client import resolve_client
from refract.emitters.python.resolve.mcp import resolve_mcp
from refract.emitters.python.resolve.models import resolve_models, resolve_shared_models
from refract.emitters.python.resolve.requests import resolve_requests
from refract.emitters.python.resolve.root_client import resolve_root_client
from refract.emitters.python.resolve.tests import resolve_tests

if TYPE_CHECKING:
    from collections.abc import Callable

    from jinja2 import Environment

    from refract import ir
    from refract.emitters.python.views import PageView


# ---- table rows ----


@dataclass(frozen=True)
class SurfaceSpec:
    """One PER-RESOURCE surface: what it is called, when it applies, how it resolves, what it
    renders through."""

    name: str
    applies: Callable[[ir.Resource], bool]
    resolve: Callable[[ir.Resource, EmitContext], PageView]
    template: str


@dataclass(frozen=True)
class DomainSurfaceSpec:
    """One PER-DOMAIN surface - the same four values over the domain's whole resource tuple."""

    name: str
    applies: Callable[[tuple[ir.Resource, ...]], bool]
    resolve: Callable[[tuple[ir.Resource, ...], EmitContext], PageView]
    template: str


# ---- generic emitters ----


class TemplateSurface(SurfaceEmitter):
    """Every per-resource surface but `package`, driven by its `SurfaceSpec` row."""

    def __init__(self, spec: SurfaceSpec, env: Environment) -> None:
        self.name = spec.name
        self._spec = spec
        self._env = env

    def applies(self, res: ir.Resource) -> bool:
        return self._spec.applies(res)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = self._spec.resolve(res, ctx)
        return self._env.get_template(self._spec.template).render(page=page)


class TemplateDomainSurface(DomainEmitter):
    """Every per-domain surface, driven by its `DomainSurfaceSpec` row. Runs ONCE over ALL of a
    domain's resources (root_client aggregates them; shared_models emits `_models.yaml` once)."""

    def __init__(self, spec: DomainSurfaceSpec, env: Environment) -> None:
        self.name = spec.name
        self._spec = spec
        self._env = env

    def applies(self, resources: tuple[ir.Resource, ...]) -> bool:
        return self._spec.applies(resources)

    def emit(self, resources: tuple[ir.Resource, ...], ctx: EmitContext) -> str:
        page = self._spec.resolve(resources, ctx)
        return self._env.get_template(self._spec.template).render(page=page)


class PackageSurface(SurfaceEmitter):
    """The `__init__.py` surface: a package marker whose whole body is the resource docstring.

    The one surface outside the table - it has no page view and no template to render, so it
    would carry two dead columns and an indirection that hides its single line of output.
    """

    name = "package"

    def applies(self, res: ir.Resource) -> bool:
        return True

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        return f'"""{res.documentation}"""\n'


# ---- the table ----

MODELS_SURFACE = SurfaceSpec("models", lambda res: bool(res.models), resolve_models, "models.jinja")
REQUESTS_SURFACE = SurfaceSpec(
    "requests", lambda res: bool(res.operations), resolve_requests, "requests.jinja"
)
CLIENT_SURFACE = SurfaceSpec(
    "client", lambda res: bool(res.operations), resolve_client, "client.jinja"
)
CLI_SURFACE = SurfaceSpec(
    "cli", lambda res: any(op.cli is not None for op in res.operations), resolve_cli, "cli.jinja"
)
MCP_SURFACE = SurfaceSpec(
    "mcp", lambda res: any(op.mcp is not None for op in res.operations), resolve_mcp, "mcp.jinja"
)
TESTS_SURFACE = SurfaceSpec(
    "tests", lambda res: any(op.tests for op in res.operations), resolve_tests, "tests.jinja"
)

ROOT_CLIENT_SURFACE = DomainSurfaceSpec(
    "root_client", lambda resources: True, resolve_root_client, "root_client.jinja"
)
SHARED_MODELS_SURFACE = DomainSurfaceSpec(
    "shared_models",
    # gated so a domain with no `_models.yaml` emits no empty shared_models.py; the tuple is
    # identical across the domain (`generation._attach_shared`), so resources[0] stands in for it
    lambda resources: bool(resources[0].shared_models),
    resolve_shared_models,
    "models.jinja",  # a shared models page IS a models page - same view, same template
)


def python_surfaces(env: Environment) -> tuple[SurfaceEmitter, ...]:
    """The per-resource surfaces, in emit order."""
    specs = (
        MODELS_SURFACE,
        REQUESTS_SURFACE,
        CLIENT_SURFACE,
        CLI_SURFACE,
        MCP_SURFACE,
        TESTS_SURFACE,
    )
    return (PackageSurface(), *(TemplateSurface(spec, env) for spec in specs))


def python_domain_surfaces(env: Environment) -> tuple[DomainEmitter, ...]:
    """The per-API glue surfaces, in emit order."""
    return tuple(
        TemplateDomainSurface(spec, env) for spec in (ROOT_CLIENT_SURFACE, SHARED_MODELS_SURFACE)
    )
