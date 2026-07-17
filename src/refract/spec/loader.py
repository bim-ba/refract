from __future__ import annotations

from typing import TYPE_CHECKING

import yaml
from pydantic import ValidationError

from refract import ir
from refract.ir.types import ListType, MapType, NeutralType, RefType, ScalarType
from refract.spec import nodes

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


def _field(spec: nodes.FieldSpec) -> ir.Field:
    return ir.Field(
        name=spec.name,
        type=parse_neutral_type(spec.type),
        optional=spec.optional,
        default=spec.default,
        alias=spec.alias,
        description=spec.description,
    )


def _param(spec: nodes.ParamSpec) -> ir.Param:
    return ir.Param(
        name=spec.name,
        loc=spec.loc,
        type=parse_neutral_type(spec.type),
        optional=spec.optional,
        default=spec.default,
        alias=spec.alias,
        help=spec.help,
    )


def _model(spec: nodes.ModelSpec) -> ir.Model:
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


def _body(spec: nodes.BodySpec | None) -> ir.Body | None:
    """by_alias/omit_none take True/True defaults; the old `dump` text is no longer lowered."""
    return None if spec is None else ir.Body(model=spec.model)


def _require_found(spec: nodes.RequireFoundSpec | None) -> ir.RequireFound | None:
    return None if spec is None else ir.RequireFound(sentinel=spec.sentinel, message=spec.message)


def _mcp(spec: nodes.McpSpec) -> ir.McpMeta:
    return ir.McpMeta(
        name=spec.name,
        safety=spec.safety,  # str -> ir.Safety StrEnum (pydantic coerces at the IR boundary)
        title=spec.title,
        documentation=spec.documentation,
        require_found=_require_found(spec.require_found),
    )


def _cli(spec: nodes.CliSpec | None) -> ir.CliMeta | None:
    return None if spec is None else ir.CliMeta(name=spec.name, documentation=spec.documentation)


def _test(spec: nodes.TestSpec) -> ir.TestCase:
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


def _response_model(responses: dict[int, nodes.ResponseSpec]) -> str:
    """The success response's model name (``responses[200].model``)."""
    return responses[200].model


def _operation(spec: nodes.OperationSpec) -> ir.Operation:
    return ir.Operation(
        name=spec.name,
        method=spec.method,
        path=spec.path,
        operation_id=spec.operation_id,
        params=tuple(_param(param) for param in spec.params),
        body=_body(spec.body),
        response_model=_response_model(spec.responses),
        documentation=spec.documentation,
        mcp=_mcp(spec.mcp),
        cli=_cli(spec.cli),
        tests=tuple(_test(test) for test in spec.tests),
        handler=spec.handler,
    )


def _module_docs(spec: nodes.ModuleDocsSpec) -> ir.ModuleDocs:
    return ir.ModuleDocs(
        client=spec.client,
        models=spec.models,
        cli=spec.cli,
        mcp=spec.mcp,
        cli_group_help=spec.cli_group_help,
        mcp_server=spec.mcp_server,
        client_class=spec.client_class,
    )


def _resource(spec: nodes.ResourceSpec) -> ir.Resource:
    return ir.Resource(
        domain=spec.domain,
        resource=spec.resource,
        security=spec.security,  # base_url dropped - now ir.ClientConfig.server.base_url
        models=tuple(_model(model) for model in spec.models),
        operations=tuple(_operation(operation) for operation in spec.operations),
        documentation=spec.documentation,
        module_docs=_module_docs(spec.module_docs),
    )


# --------------------------------------------------------------- client.yaml -> ir.ClientConfig


def _auth_input(name: str, node: nodes.AuthInputNode) -> ir.AuthInput:
    return ir.AuthInput(name=name, env=node.env)


def _auth_scheme(node: nodes.AuthSchemeNode) -> ir.AuthScheme:
    inputs = tuple(_auth_input(name, inp) for name, inp in node.inputs.items())
    if isinstance(node, nodes.MultiHeaderAuthNode):
        return ir.MultiHeaderAuth(headers=tuple(node.headers.items()), inputs=inputs)
    return ir.HeaderAuth(header=node.header, template=node.template, inputs=inputs)


def _client_config(spec: nodes.ClientConfigNode) -> ir.ClientConfig:
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
    except yaml.YAMLError as error:
        raise SpecError(f"{path}: invalid YAML - {error}") from error
    if not isinstance(raw, dict):
        raise SpecError(f"{path}: top level must be a mapping, got {type(raw).__name__}")
    return raw


class SpecLoader:
    """Parse + validate resource.yaml / client.yaml into frozen, neutral ``refract.ir``."""

    @staticmethod
    def load(path: Path) -> ir.Resource:
        raw = _read_mapping(path)
        try:
            spec = nodes.ResourceSpec.model_validate(raw)
        except ValidationError as error:
            raise SpecError(f"{path}: spec failed validation -\n{error}") from error
        return _resource(spec)

    @staticmethod
    def load_client_config(path: Path) -> ir.ClientConfig:
        raw = _read_mapping(path)
        try:
            spec = nodes.ClientConfigNode.model_validate(raw)
        except ValidationError as error:
            raise SpecError(f"{path}: client config failed validation -\n{error}") from error
        return _client_config(spec)
