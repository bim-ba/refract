"""Emit ``client.py`` — the declarative uplink transport client (HTTP lives ONLY here).

Reproduces the ycli client idioms: no ``from __future__ import annotations`` (uplink reads
annotations eagerly), the ``@uplink.returns.json()`` / ``@uplink.json`` / ``@uplink.<verb>(path)``
decorator stack, and the ``# ty: ignore[empty-body]`` empty-body method. Two method shapes render
today: a plain empty-body read (``me``'s / ``priorities``' ``list``) and a ``TypedModel`` write —
an internal bodyless-JSON ``_verb`` method the caller never touches, paired with a public ``verb``
that takes a typed pydantic body, ``model_dump``s it, and forwards to ``_verb`` (``priorities``'
``create`` / ``edit``). The offset-drain shape arrives with the first paginated listing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.python._common import (
    domain_resource_base,
    render_doc,
    resource_client_class,
)
from refract.format import ruff_format

if TYPE_CHECKING:
    from refract import ir


def _model_imports(res: ir.Resource) -> str:
    """The ``from ...models import <Model>`` line — every model a client method returns or accepts.

    Union of the response models (a method's return type) and the ``TypedModel`` body models (a
    public write method's typed ``body`` parameter), sorted; ruff wraps the line if it is long.
    """
    module = f"ycli.yandex.{res.domain}.{res.resource}.models"
    names = {op.response_model for op in res.operations if op.response_model}
    names |= {op.body.model for op in res.operations if op.body}
    return f"from {module} import {', '.join(sorted(names))}"


def _decorators(operation: ir.Operation, *, json_body: bool) -> list[str]:
    """The ``@uplink.*`` decorator stack (``@uplink.json`` only when there is a JSON body)."""
    lines = ["    @uplink.returns.json()"]
    if json_body:
        lines.append("    @uplink.json")
    lines.append(f'    @uplink.{operation.method.lower()}("{operation.path}")')
    return lines


def _simple(operation: ir.Operation) -> list[str]:
    """A plain uplink-decorated empty-body read endpoint (no request body, no params)."""
    lines = _decorators(operation, json_body=False)
    lines.append(
        f"    def {operation.name}(self) -> {operation.response_model}:  # ty: ignore[empty-body]"
    )
    lines += render_doc(operation.documentation, "        ")
    return lines


_BODY_PHRASE = {"POST": "a ready JSON body", "PATCH": "a ready body"}


def _internal_doc(operation: ir.Operation) -> str:
    """The internal ``_verb`` docstring — the raw route + a pointer to its public wrapper."""
    query_suffix = "".join(
        f"?{param.alias or param.name}=" for param in operation.params if param.loc == "query"
    )
    route = f"{operation.method} /{operation.path}{query_suffix}"
    phrase = _BODY_PHRASE[operation.method]
    return f"``{route}`` — {operation.name} from {phrase} (see ``{operation.name}``)."


def _uplink_params(operation: ir.Operation) -> list[tuple[str, str | None]]:
    """Ordered ``(source, ty-ignore-code)`` uplink params: path params, ``body``, then query."""
    rendered: list[tuple[str, str | None]] = [
        (f"{param.name}: uplink.Path", None) for param in operation.params if param.loc == "path"
    ]
    rendered.append(("body: uplink.Body", None))
    for param in operation.params:
        if param.loc == "query":
            query = f"uplink.Query({param.alias!r})" if param.alias else "uplink.Query"
            rendered.append((f"{param.name}: {query} = {param.default}", "invalid-type-form"))
    return rendered


def _internal_method(operation: ir.Operation) -> list[str]:
    """The internal bodyless-JSON ``_verb`` method (uplink params, empty body, ``model_dump``ed)."""
    lines = _decorators(operation, json_body=True)
    rendered = _uplink_params(operation)
    tail = f") -> {operation.response_model}:  # ty: ignore[empty-body]"
    if any(comment for _, comment in rendered):
        lines.append(f"    def _{operation.name}(")
        lines.append("        self,")
        for source, comment in rendered:
            suffix = f"  # ty: ignore[{comment}]" if comment else ""
            lines.append(f"        {source},{suffix}")
        lines.append(f"    {tail}")
    else:
        joined = ", ".join(source for source, _ in rendered)
        lines.append(f"    def _{operation.name}(self, {joined}{tail}")
    lines += render_doc(_internal_doc(operation), "        ")
    return lines


def _public_method(operation: ir.Operation, body: ir.Body) -> list[str]:
    """The public typed-body ``verb``: a typed signature forwarding to the internal ``_verb``."""
    path_params = [param for param in operation.params if param.loc == "path"]
    query_params = [param for param in operation.params if param.loc == "query"]
    parameters = ["self", *(f"{param.name}: {param.type}" for param in path_params)]
    parameters.append(f"body: {body.model}")
    if query_params:
        parameters.append("*")
        parameters += [f"{param.name}: {param.type} = {param.default}" for param in query_params]
    lines = [
        "",
        f"    def {operation.name}({', '.join(parameters)}) -> {operation.response_model}:",
    ]
    lines += render_doc(operation.documentation, "        ")
    arguments = [f"{param.name}={param.name}" for param in path_params]
    arguments.append(f"body=body.model_dump({body.dump})")
    arguments += [f"{param.name}={param.name}" for param in query_params]
    lines.append(f"        return self._{operation.name}({', '.join(arguments)})")
    return lines


def _method(operation: ir.Operation) -> list[str]:
    """Dispatch one operation to its client shape — a ``TypedModel`` write split or a plain read."""
    body = operation.body
    if body is not None:
        return _internal_method(operation) + _public_method(operation, body)
    return _simple(operation)


def emit(res: ir.Resource) -> str:
    """Render the whole ``client.py`` for ``res`` (ruff-formatted)."""
    out = [
        *render_doc(res.module_docs.client, ""),
        "",
        "import uplink",
        "",
        f"from ycli.yandex.{res.domain}.base import {domain_resource_base(res)}",
        _model_imports(res),
        "",
        "",
        f"class {resource_client_class(res)}({domain_resource_base(res)}):",
        *render_doc(res.module_docs.client_class, "    "),
    ]
    for operation in res.operations:
        out.append("")
        out += _method(operation)
    rendered = "\n".join(out).rstrip() + "\n"
    return ruff_format(rendered)
