from __future__ import annotations

from string import Formatter
from typing import TYPE_CHECKING, cast

import yaml
from pydantic import ValidationError

from refract import ir
from refract.ir.types import (
    ListType,
    LiteralType,
    MapType,
    NeutralType,
    RefType,
    ScalarType,
    UnionType,
)
from refract.spec import schema

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["SpecError", "SpecLoader", "parse_neutral_type"]

_SCALARS = frozenset({"string", "integer", "number", "boolean", "any"})


class SpecError(Exception):
    """A malformed spec - carries the file path and the underlying validation message."""


def _split_top_comma(inner: str) -> tuple[str, str]:
    """Split ``K,V`` on the FIRST top-level comma (bracket-depth aware)."""
    depth = 0
    for i, ch in enumerate(inner):
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        elif ch == "," and depth == 0:
            return inner[:i], inner[i + 1 :]
    raise SpecError(f"expected 'K,V' in map<...>, got {inner!r}")


def parse_neutral_type(text: str) -> NeutralType:
    """Parse one neutral spec type string into a NeutralType (see section A grammar)."""
    text = text.strip()
    if text in _SCALARS:
        return ScalarType(scalar=text)  # ty: ignore[invalid-argument-type]
    for prefix, build in (
        ("ref<", lambda body: RefType(target=body.strip())),
        ("list<", lambda body: ListType(item=parse_neutral_type(body))),
    ):
        if text.startswith(prefix) and text.endswith(">"):
            body = text[len(prefix) : -1]
            if not body.strip():
                raise SpecError(f"empty type argument in {text!r}")
            return build(body)
    if text.startswith("map<") and text.endswith(">"):
        key, value = _split_top_comma(text[4:-1])
        return MapType(key=parse_neutral_type(key), value=parse_neutral_type(value))
    raise SpecError(f"unknown neutral type: {text!r}")


# --------------------------------------------------------------------- resource.yaml -> ir.Resource


def _field(spec: schema.FieldSpec) -> ir.Field:
    if spec.type is not None and spec.oneof is not None:
        raise SpecError(f"field {spec.name!r}: set exactly one of 'type' and 'oneof', not both")
    if spec.oneof is not None:
        neutral_type: NeutralType = _oneof_type(spec.name, spec.oneof)
    elif spec.type is not None:
        neutral_type = parse_neutral_type(spec.type)
    else:
        raise SpecError(f"field {spec.name!r}: needs 'type' or 'oneof'")
    if spec.format is not None:
        if not isinstance(neutral_type, ScalarType):
            raise SpecError(f"field {spec.name!r}: format is only valid on a scalar type")
        neutral_type = neutral_type.model_copy(update={"format": spec.format})
    return ir.Field(
        name=spec.name,
        type=neutral_type,
        optional=spec.optional,
        default=spec.default,
        alias=spec.alias,
        description=spec.description,
    )


def _oneof_type(field_name: str, spec: schema.OneOfSpec) -> UnionType:
    """Lower a structured `oneof:` node to a UnionType (Variant 2: one node, both union kinds).

    Variant VALUES are neutral type-EXPRESSIONS, so an undiscriminated union may mix
    scalars/lists/refs; a discriminated union (`discriminator` set) requires every variant to be a
    `ref<Model>` (pydantic discriminated unions need BaseModel arms). Map KEYS are wire tag values
    when discriminated, documentation-only labels when not.
    """
    variants = tuple(parse_neutral_type(expr) for expr in spec.variants.values())
    if spec.discriminator is not None:
        for label, expr, variant in zip(
            spec.variants, spec.variants.values(), variants, strict=True
        ):
            if not isinstance(variant, RefType):
                raise SpecError(
                    f"field {field_name!r}: discriminated variant {label!r} must be a "
                    f"ref<Model>, got {expr!r}"
                )
    try:
        return UnionType(variants=variants, discriminator=spec.discriminator)
    except ValueError as error:  # the >= 2 validator
        raise SpecError(f"field {field_name!r}: {error}") from error


def _param(spec: schema.ParamSpec) -> ir.Param:
    # A path param fills a `{...}` slot in the URL and is therefore always required. Permitting
    # `optional`/`default` on it is a representable illegal state: every non-CLI surface appends
    # `body: <model>` (no default) after the path decls, so a defaulted path param before the body
    # renders a required-after-default SyntaxError. Reject at the boundary (make it unrepresentable)
    # rather than let it reach the emitter.
    if spec.loc == "path" and (spec.optional or spec.default is not None):
        raise SpecError(
            f"param {spec.name!r}: a path param is always required - it cannot be optional or "
            "carry a default"
        )
    return ir.Param(
        name=spec.name,
        loc=spec.loc,
        type=parse_neutral_type(spec.type),
        optional=spec.optional,
        default=spec.default,
        alias=spec.alias,
        help=spec.help,
    )


def _model(spec: schema.ModelSpec) -> ir.Model:
    """Build the Model variant `kind` selects (config dropped: dead - 0 spec/emitter uses)."""
    if spec.kind == "root_list":
        if spec.item is None:
            raise SpecError(f"model {spec.name!r}: kind=root_list requires 'item'")
        return ir.RootListModel(name=spec.name, item=spec.item, documentation=spec.documentation)
    return ir.ObjectModel(
        name=spec.name,
        fields=tuple(_field(field) for field in spec.fields),
        documentation=spec.documentation,
    )


def _synthesize_discriminators(
    models: tuple[ir.Model, ...], specs: list[schema.ModelSpec]
) -> tuple[ir.Model, ...]:
    """Inject each discriminated-union variant's synthetic `Literal[label]` field (default B).

    Variant 2: for a DISCRIMINATED `oneof` (discriminator set) every variant VALUE is a
    `ref<Model>` - ref-ness is already enforced by `_oneof_type` upstream, so the parse is
    guaranteed a RefType (the `cast` narrows it without a dead isinstance branch). An
    UNDISCRIMINATED `oneof` (discriminator None) synthesizes nothing - its labels are
    documentation only. Standalone (built models + their specs in, models out) so Task 9's
    `load_shared_models` can reuse it verbatim.

    One variant may be named by several `oneof` declarations - by two holders over the same
    variant set, or twice inside one holder's own map - so injection is keyed by
    `(variant, discriminator)`: an identical label repeats no field, while a DIFFERENT label for
    that key is a spec contradiction (one variant cannot carry two tags) and fails loud.
    """
    by_name = {model.name: model for model in models}
    injected: dict[str, list[ir.Field]] = {}  # variant model name -> synthetic tag fields
    labelled: dict[tuple[str, str], str] = {}  # (variant, discriminator) -> label already injected
    for model_spec in specs:
        for field_spec in model_spec.fields:
            oneof = field_spec.oneof
            if oneof is None or oneof.discriminator is None:
                continue
            for label, variant_expr in oneof.variants.items():
                target = cast("RefType", parse_neutral_type(variant_expr)).target
                if target not in by_name:
                    raise SpecError(
                        f"field {field_spec.name!r}: discriminated-union variant "
                        f"{target!r} is not a declared model"
                    )
                previous = labelled.get((target, oneof.discriminator))
                if previous == label:
                    continue  # this exact tag is already injected - one field, not one per holder
                if previous is not None:
                    # the first label may come from another holder, so name the CURRENT field only
                    raise SpecError(
                        f"field {field_spec.name!r}: discriminated-union variant {target!r} gets "
                        f"conflicting labels {previous!r} and {label!r} for discriminator "
                        f"{oneof.discriminator!r}"
                    )
                labelled[target, oneof.discriminator] = label
                injected.setdefault(target, []).append(
                    ir.Field(name=oneof.discriminator, type=LiteralType(value=label))
                )
    result: list[ir.Model] = []
    for model in models:
        extra = injected.get(model.name)
        if extra is None:
            result.append(model)
            continue
        if not isinstance(model, ir.ObjectModel):
            raise SpecError(f"discriminated-union variant {model.name!r} must be an object model")
        existing = {field.name for field in model.fields}
        for synthetic in extra:
            if synthetic.name in existing:
                raise SpecError(
                    f"variant {model.name!r}: field {synthetic.name!r} collides with the "
                    "synthesized discriminator"
                )
        result.append(model.model_copy(update={"fields": (*extra, *model.fields)}))
    return tuple(result)


def _body(spec: schema.BodySpec | None) -> ir.Body | None:
    """by_alias/omit_none take their True/True IR defaults; the spec has no key to override them."""
    return None if spec is None else ir.Body(model=spec.model)


def _require_found(spec: schema.RequireFoundSpec | None) -> ir.RequireFound | None:
    return None if spec is None else ir.RequireFound(sentinel=spec.sentinel, message=spec.message)


def _mcp(spec: schema.MCPToolSpec) -> ir.MCPTool:
    return ir.MCPTool(
        name=spec.name,
        safety=spec.safety,  # str -> ir.Safety StrEnum (pydantic coerces at the IR boundary)
        title=spec.title,
        documentation=spec.documentation,
        require_found=_require_found(spec.require_found),
    )


def _cli(spec: schema.CLICommandSpec | None) -> ir.CLICommand | None:
    return None if spec is None else ir.CLICommand(name=spec.name, documentation=spec.documentation)


def _test(spec: schema.TestSpec) -> ir.TestCase:
    return ir.TestCase(
        name=spec.name,
        kind=spec.kind,  # str -> ir.TestKind StrEnum (pydantic coerces)
        http_method=spec.http_method,
        path=spec.path,
        status=spec.status,
        response_json=spec.response_json,
        has_json=spec.has_json,
        asserts=tuple(spec.asserts),
        call=spec.call,
    )


def _response_model(name: str, responses: dict[int, schema.ResponseSpec]) -> str | None:
    """The first-2xx success model name, or None for a bodyless success. SpecError if no 2xx."""
    success = [status for status in responses if 200 <= status < 300]
    if not success:
        raise SpecError(f"operation {name!r} has no 2xx response")
    return responses[min(success)].model


def _path_placeholders(operation_name: str, path: str) -> frozenset[str]:
    """The `{slot}` names of `path`, read with the SAME grammar the emitter's f-string will use.

    `string.Formatter` is that grammar (`{{` is an escape, not a slot), so a naive regex disagrees
    with the emitted code exactly where it hurts: `w/{{a}}` renders the literal URL `w/{a}` and
    substitutes nothing. Only a bare `{name}` is a parameter slot, so the accepted path must ROUND
    TRIP through the parse: `Formatter` reports `{a}`, `{a:}`, `{a:>5}` and `{a!r}` alike (a plain
    field's format_spec is `''`, never None), and each dropped suffix would reach the URL - `{a:}`
    even resolves to the builtin when the emitter's shadow guard renames the local var.
    """
    if "{{" in path or "}}" in path:
        raise SpecError(
            f"operation {operation_name!r}: path {path!r} contains an escaped brace - a doubled "
            "brace renders one literal brace in the URL and substitutes no param"
        )
    try:
        slots = list(Formatter().parse(path))
    except ValueError as error:  # unbalanced brace - the emitted f-string would not even compile
        raise SpecError(
            f"operation {operation_name!r}: path {path!r} is malformed - {error}"
        ) from error
    fields: set[str] = set()
    round_trip: list[str] = []
    for literal, field, _format_spec, _conversion in slots:
        round_trip.append(literal if field is None else f"{literal}{{{field}}}")
        if field is not None:
            fields.add(field)
    if "".join(round_trip) != path or not all(field.isidentifier() for field in fields):
        raise SpecError(
            f"operation {operation_name!r}: path {path!r} has a slot that is not a plain "
            "'{parameter_name}' - a conversion, a format spec (even an empty one) or a non-name "
            "field silently changes the URL"
        )
    return frozenset(fields)


def _check_path_placeholders(spec: schema.OperationSpec) -> None:
    """The `{slots}` of `path` must be EXACTLY the declared `loc: path` param names.

    Every surface renders the path as an f-string over the path params, so a mismatch in either
    direction still imports (an f-string body is evaluated on call) and raises `NameError` on the
    first call: an unbacked placeholder names a variable nobody binds, a slotless param is dead.
    Reject both at the boundary so the illegal state never reaches the IR.
    """
    placeholders = _path_placeholders(spec.name, spec.path)
    declared = frozenset(param.name for param in spec.params if param.loc == "path")
    if placeholders != declared:
        raise SpecError(
            f"operation {spec.name!r}: path {spec.path!r} has placeholders {sorted(placeholders)} "
            f"but declares path params {sorted(declared)} - the two sets must match exactly"
        )


def _operation(spec: schema.OperationSpec) -> ir.Operation:
    _check_path_placeholders(spec)
    return ir.Operation(
        name=spec.name,
        method=spec.method,
        path=spec.path,
        operation_id=spec.operation_id,
        params=tuple(_param(param) for param in spec.params),
        body=_body(spec.body),
        response_model=_response_model(spec.name, spec.responses),
        documentation=spec.documentation,
        mcp=_mcp(spec.mcp),
        cli=_cli(spec.cli),
        tests=tuple(_test(test) for test in spec.tests),
        handler=spec.handler,
    )


def _module_docs(spec: schema.ModuleDocsSpec) -> ir.ModuleDocs:
    return ir.ModuleDocs(
        client=spec.client,
        models=spec.models,
        cli=spec.cli,
        mcp=spec.mcp,
        cli_group_help=spec.cli_group_help,
        mcp_server=spec.mcp_server,
        client_class=spec.client_class,
    )


def _resource(spec: schema.ResourceSpec) -> ir.Resource:
    models = _synthesize_discriminators(tuple(_model(model) for model in spec.models), spec.models)
    return ir.Resource(
        domain=spec.domain,
        resource=spec.resource,
        security=spec.security,  # base_url dropped - now ir.ClientConfig.server.base_url
        models=models,
        operations=tuple(_operation(operation) for operation in spec.operations),
        documentation=spec.documentation,
        module_docs=_module_docs(spec.module_docs),
    )


# --------------------------------------------------------------- client.yaml -> ir.ClientConfig


def _auth_input(name: str, node: schema.AuthInputSpec) -> ir.AuthInput:
    return ir.AuthInput(name=name, env=node.env)


def _auth_scheme(node: schema.AuthSchemeSpec) -> ir.AuthScheme:
    inputs = tuple(_auth_input(name, inp) for name, inp in node.inputs.items())
    if isinstance(node, schema.MultiHeaderAuthSpec):
        return ir.MultiHeaderAuth(headers=tuple(node.headers.items()), inputs=inputs)
    return ir.HeaderAuth(header=node.header, template=node.template, inputs=inputs)


def _client_config(spec: schema.ClientConfigSpec) -> ir.ClientConfig:
    return ir.ClientConfig(
        name=spec.name,
        server=ir.Server(base_url=spec.server.base_url),
        default_headers=tuple(spec.default_headers.items()),
        auth=tuple((name, _auth_scheme(scheme)) for name, scheme in spec.auth.items()),
    )


def _read_mapping(path: Path) -> dict:
    """Read + YAML-parse `path`, asserting a mapping top level (shared by both entry points)."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:  # missing/unreadable file or malformed YAML
        raise SpecError(f"{path}: cannot read spec - {error}") from error
    if not isinstance(raw, dict):
        raise SpecError(f"{path}: top level must be a mapping, got {type(raw).__name__}")
    return raw


class SpecLoader:
    """Parse + validate resource.yaml / client.yaml into frozen, neutral ``refract.ir``."""

    @staticmethod
    def load(path: Path) -> ir.Resource:
        raw = _read_mapping(path)
        try:
            spec = schema.ResourceSpec.model_validate(raw)
        except ValidationError as error:
            raise SpecError(f"{path}: spec failed validation -\n{error}") from error
        try:
            return _resource(spec)
        except SpecError as error:  # lowering errors name the operation/model, not the file
            raise SpecError(f"{path}: {error}") from error

    @staticmethod
    def load_client_config(path: Path) -> ir.ClientConfig:
        raw = _read_mapping(path)
        try:
            spec = schema.ClientConfigSpec.model_validate(raw)
        except ValidationError as error:
            raise SpecError(f"{path}: client config failed validation -\n{error}") from error
        return _client_config(spec)

    @staticmethod
    def load_shared_models(path: Path) -> tuple[ir.Model, ...]:
        """Load `_models.yaml` - models shared across every resource in an API. Reuses
        `_synthesize_discriminators` so a shared discriminated union is also tag-synthesized."""
        raw = _read_mapping(path)
        try:
            spec = schema.SharedModelsSpec.model_validate(raw)
        except ValidationError as error:
            raise SpecError(f"{path}: shared models failed validation -\n{error}") from error
        return _synthesize_discriminators(tuple(_model(m) for m in spec.models), spec.models)
