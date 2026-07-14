"""The typed IR — frozen, language-neutral dataclasses describing one API resource.

This is the *core product* of the generator: a spec (one YAML per resource, see
``docs/design.md``) is parsed and validated by ``refract.loader`` into these dataclasses, and
every emitter (``refract.emitters.<language>.<surface>``) reads ONLY this IR. Nothing here knows
about Python, uplink, typer, or fastmcp — those are the Python emitter's concern — so a future
``emitters/typescript/`` reads the identical IR.

Design rules:
- Everything is ``frozen=True`` (an IR value is immutable once loaded).
- Collections are tuples (hashable, non-mutable) so a ``Resource`` is itself hashable.
- Field names are spelled out in full (no abbreviations), matching the ycli house style.
- ``Field.type`` (and every other ``type``/``default`` string in this module) is the
  **already-lowered Python type-string** the emitters render verbatim (e.g. ``"int | None"``,
  default text ``"None"``). The v2 neutral spec type system (``string|integer|list<T>|...`` +
  ``optional``) lives one layer up, in the spec/loader — lowering neutral types to these strings
  is the loader's job (see ``docs/design.md`` §2), not the IR's.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "CliMeta",
    "Field",
    "McpMeta",
    "Model",
    "ModuleDocs",
    "Operation",
    "Param",
    "RequireFound",
    "Resource",
    "TestCase",
]


@dataclass(frozen=True)
class Field:
    """One field of a model.

    ``optional`` mirrors the spec-level optionality (independent of how it was lowered into
    ``type``/``default``) so downstream reasoning — e.g. whether a write-body model excludes the
    field, whether a constructor argument is required — doesn't need to re-parse ``type``.
    ``default`` is the *source text* of the default expression (e.g. ``"None"``, ``"[]"``) or
    ``None`` to mean the field has no default rendered. ``description`` becomes both a pydantic
    ``Field(description=...)`` and — for write-body models — the MCP JSON-schema description an
    agent reads.
    """

    name: str
    type: str
    optional: bool = False
    default: str | None = None
    alias: str | None = None
    description: str | None = None


@dataclass(frozen=True)
class Model:
    """A model definition. ``kind`` is ``object`` | ``root_list`` | ``envelope``.

    - ``object``    — a normal ``APIModel`` subclass with ``fields``.
    - ``root_list`` — a ``RootModel[list[<item>]]`` flat public list (``item`` names the element).
    - ``envelope``  — an internal per-page ``{links, result: [...]}`` parse type (``fields``).
    """

    name: str
    fields: tuple[Field, ...] = ()
    kind: str = "object"
    item: str | None = None
    documentation: str | None = None
    config: tuple[tuple[str, str], ...] = ()  # e.g. (("extra", "allow"),) -> ConfigDict(extra=...)


@dataclass(frozen=True)
class Param:
    """A request parameter. ``loc`` is ``path`` | ``query`` | ``body``.

    ``alias`` renders an aliased query (``uplink.Query("perPage")``); ``default`` is the source
    text of the parameter default (``"None"``, ``"0"``, ``"_PAGE_SIZE"``) or ``None`` for none.
    """

    name: str
    loc: str
    type: str = "str"
    alias: str | None = None
    default: str | None = None
    help: str | None = None


@dataclass(frozen=True)
class RequireFound:
    """The MCP empty-result guard, authored as data (not computed by the emitter).

    A GET-by-id/lookup MCP tool that can legitimately return "nothing" (a sentinel empty value,
    e.g. an empty list or ``None``) renders a guard that raises a caller-facing error instead of
    silently returning the sentinel. ``sentinel`` is the source text of the empty-result check
    (e.g. ``"not result"``); ``message`` is the error text raised when it matches.
    """

    sentinel: str
    message: str


@dataclass(frozen=True)
class McpMeta:
    """The hand-tuned MCP facet of an operation: tool name, safety annotation, title, docstring.

    ``safety`` is one of ``RO`` | ``WRITE`` | ``WRITE_IDEMPOTENT`` | ``DESTRUCTIVE`` — it drives
    the emitted ``readOnlyHint``/``destructiveHint``/``idempotentHint`` tool annotations (ARCH-3
    honesty in the ycli sense: the annotation must match what the tool actually does).
    """

    name: str
    safety: str
    title: str
    documentation: str
    require_found: RequireFound | None = None


@dataclass(frozen=True)
class CliMeta:
    """The hand-tuned CLI facet of an operation: sub-command name + one-line help."""

    name: str
    documentation: str


@dataclass(frozen=True)
class TestCase:
    """A single authored test: a hardcoded fixture + authored asserts for one surface.

    Every value here is DATA authored in the spec — the emitter never computes an assert.
    ``kind`` is ``client`` | ``cli`` | ``mcp`` | ``mcp_guard`` (which surface's harness renders
    this case; ``mcp_guard`` exercises a ``McpMeta.require_found`` guard). The stub answers
    ``http_method`` on ``BASE/path`` with ``response_json`` (ignored when ``has_json`` is
    ``False``, e.g. a 204); the test calls ``call`` and runs each string in ``asserts``.

    All nine fields are required — a ``TestCase`` is only ever assembled by the loader/test
    registry from a fully-specified fixture, never hand-defaulted by an emitter.
    """

    name: str
    kind: str
    http_method: str
    path: str
    status: int
    response_json: object | None
    has_json: bool
    asserts: tuple[str, ...]
    call: str


@dataclass(frozen=True)
class Operation:
    """One API operation across all four surfaces (client / cli / mcp / tests)."""

    name: str
    method: str
    path: str
    operation_id: str
    params: tuple[Param, ...] = ()
    response_model: str | None = None
    documentation: str | None = None
    mcp: McpMeta | None = None
    cli: CliMeta | None = None
    tests: tuple[TestCase, ...] = ()
    handler: str | None = None


@dataclass(frozen=True)
class ModuleDocs:
    """The hand-tuned module-level docstrings for a resource's four emitted surfaces.

    ``client_class``, if set, becomes the ``<Resource>Client`` class docstring (as opposed to
    ``client``, the module docstring above it). ``cli_group_help``/``mcp_server`` are the
    one-line help text for the CLI sub-command group / MCP server name, not full docstrings.
    """

    client: str | None = None
    models: str | None = None
    cli: str | None = None
    mcp: str | None = None
    cli_group_help: str | None = None
    mcp_server: str | None = None
    client_class: str | None = None


@dataclass(frozen=True)
class Resource:
    """A whole resource: its domain, name, base URL, security, models, and operations."""

    domain: str
    resource: str
    base_url: str
    security: str
    models: tuple[Model, ...]
    operations: tuple[Operation, ...]
    documentation: str | None = None
    module_docs: ModuleDocs = ModuleDocs()

    # ---- convenience accessors the emitters use ----

    def model(self, name: str) -> Model:
        """The model named ``name`` (raises ``KeyError`` if the spec never declared it)."""
        for candidate in self.models:
            if candidate.name == name:
                return candidate
        raise KeyError(name)

    @property
    def domain_title(self) -> str:
        """The domain name capitalized for prose (``tracker`` -> ``Tracker``)."""
        return self.domain.capitalize()
