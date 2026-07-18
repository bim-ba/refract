from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from refract import ir
    from refract.ir.types import NeutralType

# ---- value objects ----


@dataclass(frozen=True)
class Import:
    """One `from <module> import <name>` atom; the assembler groups + isort-sorts them."""

    module: str
    name: str


@dataclass(frozen=True)
class RenderedType:
    """A language type rendered from a NeutralType, plus the imports it pulls in."""

    text: str
    imports: tuple[Import, ...] = ()
    discriminator: str | None = None  # sibling tag field name, if this is a discriminated union
    coercer: str | None = None  # name of a hand-written `BeforeValidator` callable, if formatted


@dataclass(frozen=True)
class EmitContext:
    """Per-generation config beyond the resource itself."""

    package_root: str  # where runtime/base/models live, e.g. "ycli.yandex.tracker"
    config: ir.ClientConfig | None = None  # per-API glue; only tests (base_url) + root_client
    # read it; per-resource surfaces (requests/client/models/cli/mcp/package) ignore it, hence
    # the None default.


# ---- 5 injected strategies (ABCs) ----


class Naming(ABC):
    @abstractmethod
    def pascal(self, name: str) -> str: ...
    @abstractmethod
    # module-level def-safe: list -> list_
    def module_function(self, name: str) -> str: ...
    @abstractmethod
    # parameter-identifier-safe: id -> id_ (the caller preserves the wire name)
    def safe_param(self, name: str) -> str: ...
    @abstractmethod
    # merges the 3 *_class helpers
    def class_name(self, base: str, suffix: str) -> str: ...
    @abstractmethod
    # snake-join a flat typer option name: cli_option("name", "ru") -> "name_ru"
    def cli_option(self, *parts: str) -> str: ...


class TypeMapper(ABC):
    @abstractmethod
    def render(self, neutral_type: NeutralType, *, optional: bool) -> RenderedType: ...
    @abstractmethod
    def null_default(self, neutral_type: NeutralType, *, optional: bool) -> str | None: ...


class Formatter(ABC):
    @abstractmethod
    def format(self, source: str) -> str: ...


class Docstrings(ABC):
    @abstractmethod
    def render(self, text: str | None, indent: str) -> tuple[str, ...]: ...


class Layout(ABC):
    @abstractmethod
    def path(self, res: ir.Resource, surface: str) -> str: ...


# ---- renderer / assembler / surface / backend ----


class SurfaceEmitter(ABC):
    """One PER-RESOURCE surface plugin: gates on data presence, emits UNformatted source.

    `name` stays a plain str (NOT an enum): dispatch is registry + `applies()`, never
    name-compare; surface is the extension axis. A unit test enforces the name<->`Layout.path`
    coupling (decision #22).
    """

    name: str  # "requests" | "client" | "models" | "cli" | "mcp" | "tests" | "package"

    @abstractmethod
    def applies(self, res: ir.Resource) -> bool: ...
    @abstractmethod
    def emit(self, res: ir.Resource, ctx: EmitContext) -> str: ...


class DomainEmitter(ABC):
    """One PER-DOMAIN (per-API) surface = the generated glue. Runs ONCE over ALL resources.

    root_client aggregates resources + builds Session/`httpx.Client(auth=...)` from `ctx.config`.
    """

    name: str  # "root_client"

    @abstractmethod
    def emit(self, resources: tuple[ir.Resource, ...], ctx: EmitContext) -> str: ...


@dataclass(frozen=True)
class LanguageBackend:
    """Pure composition of the 5 strategies + surface emitters. Built by a @backend factory."""

    name: str
    naming: Naming
    type_mapper: TypeMapper
    formatter: Formatter
    docstrings: Docstrings
    layout: Layout
    surfaces: tuple[SurfaceEmitter, ...]  # per-resource
    domain_surfaces: tuple[DomainEmitter, ...] = ()  # per-API glue (root_client)
