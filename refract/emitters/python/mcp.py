"""Emit ``mcp.py`` — the fastmcp tool module (ARCH-3 honest annotations, Depends DI).

Reproduces the ycli MCP idioms: ``mcp = FastMCP("<domain>-<resource>")`` and one
``@mcp.tool(name=…, annotations={**<SAFETY>, "title": …}, tags=<TAGS>)``-decorated function per
operation. The safety class drives the annotation symbol and the tags constant (reads: ``RO`` +
``TAGS``; writes: ``WRITE``/``WRITE_IDEMPOTENT`` + ``WRITE_TAGS``). Each tool's signature carries
the operation's non-DI arguments (path params, a typed ``body``, query params) ahead of the
``client: <Domain>Client = Depends(<domain>_client)`` provider, and forwards them to the client
call. An operation with a ``require_found`` facet renders an empty-result guard; one without
returns the client call directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.python._common import domain_client_class, function_name, render_doc
from refract.format import ruff_format

if TYPE_CHECKING:
    from refract import ir


def _tags_symbol(safety: str) -> str:
    """The tags constant for a safety class (reads: ``TAGS``; writes: ``WRITE_TAGS``)."""
    return "TAGS" if safety == "RO" else "WRITE_TAGS"


def _dependency_names(res: ir.Resource) -> list[str]:
    """The names imported from ``<domain>.dependencies`` (safety annotations + tags + provider)."""
    names = {f"{res.domain}_client"}
    for operation in res.operations:
        meta = operation.mcp
        assert meta is not None  # every operation carries an mcp facet
        names.add(meta.safety)
        names.add(_tags_symbol(meta.safety))
    return sorted(names)


def _requires_guard(res: ir.Resource) -> bool:
    """Whether any operation renders a ``require_found`` guard (drives the import)."""
    return any(op.mcp is not None and op.mcp.require_found is not None for op in res.operations)


def _imports(res: ir.Resource) -> list[str]:
    """The third-party (fastmcp) + first-party (ycli.*, isort-sorted) import blocks."""
    client_module = f"ycli.yandex.{res.domain}.client"
    dependencies_module = f"ycli.yandex.{res.domain}.dependencies"
    models_module = f"ycli.yandex.{res.domain}.{res.resource}.models"
    model_names = {op.response_model for op in res.operations if op.response_model}
    model_names |= {op.body.model for op in res.operations if op.body is not None}
    models = sorted(model_names)

    first_party = [
        (client_module, f"from {client_module} import {domain_client_class(res)}"),
        (
            dependencies_module,
            f"from {dependencies_module} import {', '.join(_dependency_names(res))}",
        ),
        (models_module, f"from {models_module} import {', '.join(models)}"),
    ]
    if _requires_guard(res):
        first_party.append(("ycli.yandex.models", "from ycli.yandex.models import require_found"))

    lines = [
        "from fastmcp import FastMCP",
        "from fastmcp.dependencies import Depends",
        "",
    ]
    lines += [line for _module, line in sorted(first_party, key=lambda entry: entry[0])]
    return lines


def _signature_parameters(res: ir.Resource, operation: ir.Operation) -> list[str]:
    """The tool params in order: path params, typed ``body``, query params, then the DI client."""
    parameters = [
        f"{param.name}: {param.type}" for param in operation.params if param.loc == "path"
    ]
    if operation.body is not None:
        parameters.append(f"body: {operation.body.model}")
    parameters += [
        f"{param.name}: {param.type} = {param.default}"
        for param in operation.params
        if param.loc == "query"
    ]
    parameters.append(f"client: {domain_client_class(res)} = Depends({res.domain}_client)")
    return parameters


def _call_arguments(operation: ir.Operation) -> str:
    """The args forwarded to the client call: path params, ``body``, then keyword query params."""
    arguments = [param.name for param in operation.params if param.loc == "path"]
    if operation.body is not None:
        arguments.append("body")
    arguments += [
        f"{param.name}={param.name}" for param in operation.params if param.loc == "query"
    ]
    return ", ".join(arguments)


def _tool(res: ir.Resource, operation: ir.Operation) -> list[str]:
    """One ``@mcp.tool`` function forwarding to the client (guarded when ``require_found``)."""
    meta = operation.mcp
    assert meta is not None  # every operation carries an mcp facet
    annotations = f'{{**{meta.safety}, "title": "{meta.title}"}}'
    decorator = (
        f'@mcp.tool(name="{meta.name}", annotations={annotations}, '
        f"tags={_tags_symbol(meta.safety)})"
    )
    parameters = ", ".join(_signature_parameters(res, operation))
    signature = f"def {function_name(operation.name)}({parameters}) -> {operation.response_model}:"
    call = f"client.{res.resource}.{operation.name}({_call_arguments(operation)})"
    guard = meta.require_found
    if guard is None:
        body = [f"    return {call}"]
    else:
        body = [
            f"    result = {call}",
            "    return require_found("
            f"result, sentinel=lambda r: {guard.sentinel}, "
            f'message="{guard.message}")',
        ]
    return [decorator, signature, *render_doc(meta.documentation, "    "), *body]


def emit(res: ir.Resource) -> str:
    """Render the whole ``mcp.py`` for ``res`` (ruff-formatted)."""
    out = [
        f'"""{res.module_docs.mcp}"""',
        "",
        *_imports(res),
        "",
        f'mcp = FastMCP("{res.module_docs.mcp_server}")',
    ]
    for operation in res.operations:
        out += ["", "", *_tool(res, operation)]
    rendered = "\n".join(out).rstrip() + "\n"
    return ruff_format(rendered)
