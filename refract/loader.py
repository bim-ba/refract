"""Spec-validation layer: parse+validate ``resource.yaml`` (pydantic) -> frozen ``refract.ir``.

The pydantic models here mirror the authored v2 YAML one-to-one and set ``extra="forbid"``, so a
typo or a missing required key is rejected with a clear, located error *before* any emitter runs.
Validated specs are then lowered into the immutable ``refract.ir`` dataclasses the emitters
consume (``docs/design.md`` §§1-5) — the pydantic layer never leaks past this module.

Neutral-type lowering (``_lower_type``) is the one place the v2 neutral type system
(``docs/design.md`` §2: ``string|integer|number|boolean|any`` + ``optional``) is realized for
Python. Only the scalar map is implemented today: ``list<T>``/``map<K,V>``/``ref<Model>`` are
declared in the design doc but unused by the ``me`` resource, so — per the Task 3 brief's YAGNI
instruction — they are left for whichever resource first needs a container/reference type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from refract import ir

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["SpecError", "load"]


_SCALAR_TYPES: dict[str, str] = {
    "string": "str",
    "integer": "int",
    "number": "float",
    "boolean": "bool",
    "any": "Any",
}


class SpecError(Exception):
    """A malformed spec — carries the file path and the underlying validation message."""


# --------------------------------------------------------------------------------- spec nodes


class _Spec(BaseModel):
    """Base for every spec node: reject unknown keys so a malformed spec fails loudly."""

    model_config = ConfigDict(extra="forbid")


class FieldSpec(_Spec):
    """One neutral field of a model — mirrors a v2 ``fields:`` entry."""

    name: str
    type: str
    optional: bool = False
    default: str | None = None  # explicit spec default; None => let _lower_type decide
    alias: str | None = None
    description: str | None = None
    enum: list[str] | None = None
    format: str | None = None
    deprecated: bool = False


class ModelSpec(_Spec):
    name: str
    documentation: str | None = None
    kind: Literal["object", "root_list", "envelope"] = "object"
    item: str | None = None
    config: dict[str, str] = Field(default_factory=dict)
    fields: list[FieldSpec] = Field(default_factory=list)


class ResponseSpec(_Spec):
    model: str


class RequireFoundSpec(_Spec):
    sentinel: str
    message: str


class McpSpec(_Spec):
    name: str
    safety: Literal["RO", "WRITE", "WRITE_IDEMPOTENT", "DESTRUCTIVE"]
    title: str
    documentation: str
    require_found: RequireFoundSpec | None = None


class CliSpec(_Spec):
    name: str
    documentation: str


class TestSpec(_Spec):
    """One authored test fixture. All nine ``ir.TestCase`` fields, each with a safe default.

    Some ``kind``s (e.g. ``cli``) don't map onto a single evaluable expression, so ``call``
    defaults to ``""`` rather than being required — this keeps the node flexible enough that
    Task 6 can adjust fixture data without changing the loader (see task-3-report.md).
    """

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
    responses: dict[int, ResponseSpec]
    mcp: McpSpec
    cli: CliSpec
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
    base_url: str
    security: str
    module_docs: ModuleDocsSpec = Field(default_factory=ModuleDocsSpec)
    documentation: str | None = None
    models: list[ModelSpec] = Field(default_factory=list)
    operations: list[OperationSpec]


# --------------------------------------------------------------------------- neutral-type lowering


def _lower_type(neutral: str, optional: bool) -> tuple[str, str | None]:
    """Lower one neutral spec type to ``(python_type_string, implied_default)``.

    E.g. ``_lower_type("integer", True)`` -> ``("int | None", "None")`` — the golden's
    ``uid: int | None = None``. The implied default is the Python literal ``"None"`` (as source
    text) whenever the field is optional; callers only use it when the spec gave no explicit
    ``default`` of their own.
    """
    python_type = _SCALAR_TYPES[neutral]
    default = None
    if optional:
        python_type = f"{python_type} | None"
        default = "None"
    return python_type, default


# --------------------------------------------------------------------------------- lowering to IR


def _field(spec: FieldSpec) -> ir.Field:
    python_type, implied_default = _lower_type(spec.type, spec.optional)
    return ir.Field(
        name=spec.name,
        type=python_type,
        optional=spec.optional,
        default=spec.default if spec.default is not None else implied_default,
        alias=spec.alias,
        description=spec.description,
    )


def _model(spec: ModelSpec) -> ir.Model:
    return ir.Model(
        name=spec.name,
        fields=tuple(_field(field) for field in spec.fields),
        kind=spec.kind,
        item=spec.item,
        documentation=spec.documentation,
        config=tuple(spec.config.items()),
    )


def _require_found(spec: RequireFoundSpec | None) -> ir.RequireFound | None:
    return None if spec is None else ir.RequireFound(sentinel=spec.sentinel, message=spec.message)


def _mcp(spec: McpSpec) -> ir.McpMeta:
    return ir.McpMeta(
        name=spec.name,
        safety=spec.safety,
        title=spec.title,
        documentation=spec.documentation,
        require_found=_require_found(spec.require_found),
    )


def _cli(spec: CliSpec) -> ir.CliMeta:
    return ir.CliMeta(name=spec.name, documentation=spec.documentation)


def _test(spec: TestSpec) -> ir.TestCase:
    return ir.TestCase(
        name=spec.name,
        kind=spec.kind,
        http_method=spec.http_method,
        path=spec.path,
        status=spec.status,
        response_json=spec.response_json,
        has_json=spec.has_json,
        asserts=tuple(spec.asserts),
        call=spec.call,
    )


def _response_model(responses: dict[int, ResponseSpec]) -> str:
    """The success response's model name (``responses[200].model``; §5: derived public type)."""
    return responses[200].model


def _operation(spec: OperationSpec) -> ir.Operation:
    return ir.Operation(
        name=spec.name,
        method=spec.method,
        path=spec.path,
        operation_id=spec.operation_id,
        response_model=_response_model(spec.responses),
        documentation=spec.documentation,
        mcp=_mcp(spec.mcp),
        cli=_cli(spec.cli),
        tests=tuple(_test(test) for test in spec.tests),
        handler=spec.handler,
    )


def _module_docs(spec: ModuleDocsSpec) -> ir.ModuleDocs:
    return ir.ModuleDocs(
        client=spec.client,
        models=spec.models,
        cli=spec.cli,
        mcp=spec.mcp,
        cli_group_help=spec.cli_group_help,
        mcp_server=spec.mcp_server,
        client_class=spec.client_class,
    )


def _resource(spec: ResourceSpec) -> ir.Resource:
    return ir.Resource(
        domain=spec.domain,
        resource=spec.resource,
        base_url=spec.base_url,
        security=spec.security,
        models=tuple(_model(model) for model in spec.models),
        operations=tuple(_operation(operation) for operation in spec.operations),
        documentation=spec.documentation,
        module_docs=_module_docs(spec.module_docs),
    )


def load(path: Path) -> ir.Resource:
    """Parse + validate the ``resource.yaml`` at ``path`` and lower it to a frozen ``ir.Resource``.

    Raises :class:`SpecError` — carrying the file path and the underlying message — on invalid
    YAML, a non-mapping top level, or any pydantic validation failure (unknown key, missing
    required key, wrong type, ...).
    """
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise SpecError(f"{path}: invalid YAML — {error}") from error
    if not isinstance(raw, dict):
        raise SpecError(f"{path}: top level must be a mapping, got {type(raw).__name__}")
    try:
        spec = ResourceSpec.model_validate(raw)
    except ValidationError as error:
        raise SpecError(f"{path}: spec failed validation —\n{error}") from error
    return _resource(spec)
