"""Input schema: pydantic nodes mirroring authored resource.yaml + client.yaml one-to-one.

Every node sets ``extra="forbid"`` so a typo or a missing required key is rejected with a
located error before any emitter runs. Types stay raw here (``FieldSpec.type: str | None``,
mutually exclusive with ``FieldSpec.oneof``); the loader parses them into the neutral
``NeutralType`` and lowers the nodes into frozen ``refract.ir``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ClientConfigSpec", "ResourceSpec", "SharedModelsSpec"]


class _Spec(BaseModel):
    """Base for every spec node: reject unknown keys so a malformed spec fails loudly."""

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------- resource.yaml nodes


class OneOfSpec(_Spec):
    """Variant 2: ONE structured ``oneof:`` node for BOTH union kinds (owner-selected).

    ``variants`` maps a label to a neutral type-EXPRESSION parsed by ``parse_neutral_type``
    (e.g. ``"ref<Paragraph>"``, ``"string"``, ``"list<ref<X>>"``) - NOT a bare model name. When
    ``discriminator`` is set (discriminated), every variant must resolve to a ``ref<Model>``
    (pydantic discriminated unions need BaseModel arms); the loader enforces this fail-loud. When
    ``discriminator`` is ``None`` (undiscriminated), variants may be any neutral type and the map
    keys are documentation-only labels with no wire meaning.
    """

    variants: dict[str, str]
    discriminator: str | None = None


class FieldSpec(_Spec):
    """One neutral field of a model - mirrors a v2 ``fields:`` entry."""

    name: str
    type: str | None = None  # sentinel None: absent when `oneof:` is used instead
    optional: bool = False
    default: str | None = None  # explicit spec default; None => let the TypeMapper decide
    alias: str | None = None
    description: str | None = None
    enum: list[str] | None = None
    format: str | None = None
    deprecated: bool = False
    oneof: OneOfSpec | None = None  # mutually exclusive with `type:`


class ModelSpec(_Spec):
    name: str
    documentation: str | None = None
    kind: Literal["object", "root_list"] = "object"  # envelope deferred (no IR variant yet)
    item: str | None = None  # required for root_list; loader enforces
    fields: list[FieldSpec] = Field(default_factory=list)


class ResponseSpec(_Spec):
    model: str | None = None  # None => bodyless success (204/201-no-content)


class RequireFoundSpec(_Spec):
    sentinel: str
    message: str


class MCPToolSpec(_Spec):
    name: str
    safety: Literal["RO", "WRITE", "WRITE_IDEMPOTENT", "DESTRUCTIVE"]
    title: str
    documentation: str
    require_found: RequireFoundSpec | None = None


class CLICommandSpec(_Spec):
    name: str
    documentation: str


class ParamSpec(_Spec):
    """One neutral request parameter - mirrors a v2 ``params:`` entry (``loc`` is path|query)."""

    name: str
    loc: Literal["path", "query"]
    type: str = "string"
    optional: bool = False
    default: str | None = None
    alias: str | None = None
    help: str | None = None


class BodySpec(_Spec):
    """The write-body registry entry - only the ``TypedModel`` mode today.

    ``model`` names a hand-written body model declared in ``models:``. ``strategy``/``dump`` are
    still accepted on input (authored YAML), but the IR now carries ``by_alias``/``omit_none``
    booleans (default True/True) instead of a rendered dump string - the loader ignores ``dump``.
    """

    strategy: Literal["TypedModel"]
    model: str
    dump: str


class TestSpec(_Spec):
    """One authored test fixture - all nine ``ir.TestCase`` fields, each with a safe default."""

    name: str
    kind: Literal["client", "cli", "mcp", "mcp_guard"]
    http_method: Literal["GET", "POST", "PATCH", "DELETE"]
    path: str
    status: int = 200
    response_json: Any = None
    has_json: bool = True
    asserts: list[str] = Field(default_factory=list)
    call: str = ""


class OperationSpec(_Spec):
    name: str
    method: Literal["GET", "POST", "PATCH", "DELETE"]
    path: str
    operation_id: str = Field(alias="operationId")
    documentation: str | None = None
    params: list[ParamSpec] = Field(default_factory=list)
    body: BodySpec | None = None
    responses: dict[int, ResponseSpec]
    mcp: MCPToolSpec
    cli: CLICommandSpec | None = None
    tests: list[TestSpec] = Field(default_factory=list)
    handler: str | None = None


class ModuleDocsSpec(_Spec):
    client: str | None = None
    models: str | None = None
    cli: str | None = None
    mcp: str | None = None
    cli_group_help: str | None = None
    mcp_server: str | None = None
    client_class: str | None = None


class ResourceSpec(_Spec):
    domain: str
    resource: str
    security: str  # names an AuthScheme in client.yaml; base_url moved out to client.yaml
    module_docs: ModuleDocsSpec = Field(default_factory=ModuleDocsSpec)
    documentation: str | None = None
    models: list[ModelSpec] = Field(default_factory=list)
    operations: list[OperationSpec]


# ------------------------------------------------------------------------ _models.yaml nodes


class SharedModelsSpec(_Spec):
    """Mirrors ``_models.yaml``: models shared across every resource.yaml in an API (the k8s
    ``ObjectMeta`` anchor). Reuses the EXACT ``ModelSpec`` shape resource.yaml uses."""

    models: list[ModelSpec] = Field(default_factory=list)


# ------------------------------------------------------------------------- client.yaml nodes


class AuthInputSpec(_Spec):
    """One named credential input; the input NAME is the mapping key (loader threads it in)."""

    env: str | None = None  # env var name; None -> must be passed explicitly


class HeaderAuthSpec(_Spec):
    """Single templated header, e.g. ``Authorization: Bearer {oauth_token}`` (bearer-majority)."""

    kind: Literal["header"] = "header"
    header: str
    template: str
    inputs: dict[str, AuthInputSpec]  # MAPPING; loader -> tuple[ir.AuthInput, ...]


class MultiHeaderAuthSpec(_Spec):
    """>=1 templated headers (Yandex ``OAuth {oauth_token}`` + ``X-Org-Id``)."""

    kind: Literal["multi_header"] = "multi_header"
    headers: dict[str, str]  # MAPPING; loader -> tuple[(name, template), ...]
    inputs: dict[str, AuthInputSpec]  # MAPPING; loader -> tuple[ir.AuthInput, ...]


AuthSchemeSpec = Annotated[HeaderAuthSpec | MultiHeaderAuthSpec, Field(discriminator="kind")]


class ServerSpec(_Spec):
    base_url: str


class ClientConfigSpec(_Spec):
    """Mirrors client.yaml: server + default headers + named auth schemes."""

    name: str
    server: ServerSpec
    default_headers: dict[str, str] = Field(default_factory=dict)  # MAPPING -> tuple-of-pairs
    auth: dict[str, AuthSchemeSpec] = Field(default_factory=dict)  # scheme-name -> scheme
