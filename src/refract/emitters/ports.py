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


class DocComments(ABC):
    @abstractmethod
    def render(self, text: str | None, indent: str) -> tuple[str, ...]: ...


class FileLayout(ABC):
    @abstractmethod
    def path(self, res: ir.Resource, surface: str) -> str: ...


# ---- per-generation context ----


@dataclass(frozen=True)
class EmitContext:
    """Everything a resolver reads beyond the resource itself: the target package, the per-API
    glue config, and the three strategies the resolvers call.

    The strategies ride here rather than through every resolver signature: a resolver that needs
    none takes the same one argument as a resolver that needs all three, so adding a strategy call
    to a leaf helper is a local edit instead of a threading change up its whole call chain. The
    backend still OWNS them (`LanguageBackend`); `Generator` copies them onto the context it builds
    per resource/domain, so a backend is still composed exactly once, at the composition root.
    """

    package_root: str  # where runtime/base/models live, e.g. "ycli.yandex.tracker"
    config: ir.ClientConfig  # per-API glue; only tests (base_url) + root_client read it
    naming: Naming
    type_mapper: TypeMapper
    doc_comments: DocComments


# ---- renderer / assembler / surface / backend ----


class SurfaceEmitter(ABC):
    """One PER-RESOURCE surface plugin: gates on data presence, emits UNformatted source.

    `name` stays a plain str (NOT an enum): dispatch is registry + `applies()`, never
    name-compare; surface is the extension axis. A unit test enforces the name<->`FileLayout.path`
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

    name: str  # "root_client" | "shared_models"

    def applies(self, resources: tuple[ir.Resource, ...]) -> bool:
        """Gate before `render_domain` emits + writes a file. Defaults True (root_client always
        applies); a surface gated on domain-level data presence (e.g. shared_models, empty when
        no `_models.yaml`) overrides this to skip emitting an empty file."""
        return True

    @abstractmethod
    def emit(self, resources: tuple[ir.Resource, ...], ctx: EmitContext) -> str: ...


@dataclass(frozen=True)
class LanguageBackend:
    """Pure composition of the 5 strategies + surface emitters. Built by a @backend factory."""

    name: str
    naming: Naming
    type_mapper: TypeMapper
    formatter: Formatter
    doc_comments: DocComments
    file_layout: FileLayout
    surfaces: tuple[SurfaceEmitter, ...]  # per-resource
    domain_surfaces: tuple[DomainEmitter, ...] = ()  # per-API glue (root_client)

    def context(self, package_root: str, config: ir.ClientConfig) -> EmitContext:
        """The `EmitContext` a resolver of THIS backend reads: the caller's per-generation values
        plus this backend's own three strategies.

        The single place a context is built, so a resolver can never be handed one backend's
        strategies while emitting through another's templates."""
        return EmitContext(
            package_root=package_root,
            config=config,
            naming=self.naming,
            type_mapper=self.type_mapper,
            doc_comments=self.doc_comments,
        )
