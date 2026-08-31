from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator
from pydantic import Field as PydanticField  # `Field` (below) is the IR model-field class

from refract.ir.types import NeutralType


class _IR(BaseModel):
    model_config = ConfigDict(frozen=True)


class Safety(StrEnum):
    RO = "RO"
    WRITE = "WRITE"
    WRITE_IDEMPOTENT = "WRITE_IDEMPOTENT"
    DESTRUCTIVE = "DESTRUCTIVE"


class TestKind(StrEnum):
    CLIENT = "client"
    CLI = "cli"
    MCP = "mcp"
    MCP_GUARD = "mcp_guard"


class Field(_IR):
    name: str
    type: NeutralType
    optional: bool = False
    default: str | None = None  # source text of an *explicit* spec default; else None
    alias: str | None = None
    description: str | None = None


class ObjectModel(_IR):
    """A pydantic ``APIModel`` subclass with typed fields."""

    kind: Literal["object"] = "object"
    name: str
    fields: tuple[Field, ...] = ()
    documentation: str | None = None


class RootListModel(_IR):
    """A ``RootModel[list[item]]`` public list."""

    kind: Literal["root_list"] = "root_list"
    name: str
    item: str
    documentation: str | None = None


# discriminated union: `item` only on root_list, `fields` only on object -> illegal states
# unrepresentable. envelope (paginated wrapper) is added WITH pagination, not speculatively.
# dead `config` field dropped (0 spec instances, 0 emitter readers).
Model = Annotated[ObjectModel | RootListModel, PydanticField(discriminator="kind")]


class Param(_IR):
    name: str
    loc: Literal["path", "query"]
    type: NeutralType
    optional: bool = False
    default: str | None = None
    alias: str | None = None
    help: str | None = None


class Body(_IR):
    mode: Literal["typed_model"] = "typed_model"
    model: str
    by_alias: bool = True  # -> model_dump(by_alias=...) rendered by the Python backend
    omit_none: bool = True  # -> model_dump(exclude_none=...) rendered by the Python backend


class RequireFound(_IR):
    sentinel: str
    message: str


class MCPTool(_IR):
    name: str
    safety: Safety
    title: str
    documentation: str
    require_found: RequireFound | None = None


class CLICommand(_IR):
    name: str
    documentation: str


class TestCase(_IR):
    """One authored test fixture. ``path_args`` binds each of the operation's path params to the
    literal URL segment this case exercises (ordered, hashable - the ``ClientConfig.auth`` idiom),
    so the emitter can build the mocked URL the same way the generated client builds the real one.
    The dead ``path`` field it replaces duplicated ``Operation.path`` verbatim and was read by
    nothing.
    """

    name: str
    kind: TestKind
    http_method: str
    path_args: tuple[tuple[str, str], ...] = ()  # path-param name -> literal URL segment
    status: int
    response_json: (
        JsonValue | None
    )  # opaque JSON fixture; validated-at-boundary, repr()'d into tests
    has_json: bool  # carried for fidelity; not yet read by any emitter
    asserts: tuple[str, ...]
    call: str


# A test case renders THROUGH the facet its kind names: a `cli` case invokes `cli.name`, an `mcp`
# or `mcp_guard` case calls `mcp.name`. A `client` case needs no facet, so it is absent here.
_FACET_FOR_TEST_KIND = {TestKind.CLI: "cli", TestKind.MCP: "mcp", TestKind.MCP_GUARD: "mcp"}


class Operation(_IR):
    name: str
    method: str
    path: str
    operation_id: str  # carried for fidelity; not yet read by any emitter
    params: tuple[Param, ...] = ()
    body: Body | None = None
    response_model: str | None = None
    documentation: str | None = None
    mcp: MCPTool | None = None
    cli: CLICommand | None = None
    tests: tuple[TestCase, ...] = ()
    handler: str | None = None  # carried for fidelity; not yet read by any emitter

    @model_validator(mode="after")
    def _tests_have_the_facet_their_kind_names(self) -> Operation:
        """A ``cli``-kind test on an operation with no ``cli:`` facet (or an ``mcp``-kind one with
        no ``mcp:``) has no command to invoke - the emitted test could only ever fail.

        Enforced on the TYPE, not only in the spec loader, so any IR producer building the illegal
        combo fails at construction; through ``SpecLoader`` it surfaces as a ``SpecError`` naming
        the file, where it used to reach the tests emitter as a bare ``ValueError``.
        """
        for case in self.tests:
            facet = _FACET_FOR_TEST_KIND.get(case.kind)
            if facet is not None and getattr(self, facet) is None:
                raise ValueError(
                    f"operation {self.name!r}: test {case.name!r} is {case.kind.value}-kind but "
                    f"the operation declares no {facet!r} facet"
                )
        return self


class ModuleDocs(_IR):
    client: str | None = None
    models: str | None = None
    cli: str | None = None
    mcp: str | None = None
    cli_group_help: str | None = None
    mcp_server: str | None = None
    client_class: str | None = None
    requests: str | None = None  # docstring for the _requests module (D)


class Resource(_IR):
    domain: str
    resource: str
    security: str  # names an AuthScheme in ClientConfig.auth (base_url moved to ClientConfig)
    models: tuple[Model, ...]
    operations: tuple[Operation, ...]
    documentation: str | None = None
    module_docs: ModuleDocs = ModuleDocs()
    shared_models: tuple[Model, ...] = ()  # from _models.yaml; attached by Generator.plan

    def model(self, name: str) -> Model:
        """Local-first lookup: a name in `models` wins; a name only in `shared_models` falls
        back. A name in BOTH is rejected eagerly at plan time (`generation._attach_shared`), so
        this never has to arbitrate a collision."""
        for candidate in self.models:
            if candidate.name == name:
                return candidate
        for candidate in self.shared_models:
            if candidate.name == name:
                return candidate
        raise KeyError(name)

    @property
    def domain_title(self) -> str:
        return self.domain.capitalize()
