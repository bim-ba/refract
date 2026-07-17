from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, JsonValue
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


class McpMeta(_IR):
    name: str
    safety: Safety
    title: str
    documentation: str
    require_found: RequireFound | None = None


class CliMeta(_IR):
    name: str
    documentation: str


class TestCase(_IR):
    name: str
    kind: TestKind
    http_method: str
    path: str
    status: int
    response_json: (
        JsonValue | None
    )  # opaque JSON fixture; validated-at-boundary, repr()'d into tests
    has_json: bool
    asserts: tuple[str, ...]
    call: str


class Operation(_IR):
    name: str
    method: str
    path: str
    operation_id: str
    params: tuple[Param, ...] = ()
    body: Body | None = None
    response_model: str | None = None
    documentation: str | None = None
    mcp: McpMeta | None = None
    cli: CliMeta | None = None
    tests: tuple[TestCase, ...] = ()
    handler: str | None = None


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

    def model(self, name: str) -> Model:
        for candidate in self.models:
            if candidate.name == name:
                return candidate
        raise KeyError(name)

    @property
    def domain_title(self) -> str:
        return self.domain.capitalize()
