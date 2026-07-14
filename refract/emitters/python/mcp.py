"""Emit ``mcp.py`` — the fastmcp tool module (ARCH-3 honest annotations, Depends DI).

Reproduces the ycli MCP idioms for the ``me`` walking skeleton: ``mcp = FastMCP("<domain>-...")``;
one ``@mcp.tool(name=…, annotations={**RO, "title": …}, tags=TAGS)`` read tool whose last
parameter is ``client: <Domain>Client = Depends(<domain>_client)``, returning the response model
through a ``require_found`` empty-result guard. The write/destructive safety classes, tool
parameters, and no-guard reads arrive with the resources that need them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.python._common import domain_client_class
from refract.format import ruff_format

if TYPE_CHECKING:
    from refract import ir


def _dependency_names(res: ir.Resource) -> list[str]:
    """The names imported from ``<domain>.dependencies`` (safety annotation + tags + provider)."""
    names = {f"{res.domain}_client", "TAGS"}
    for operation in res.operations:
        meta = operation.mcp
        assert meta is not None  # every me operation carries an mcp facet
        names.add(meta.safety)
    return sorted(names)


def _imports(res: ir.Resource) -> list[str]:
    """The third-party (fastmcp) + first-party (ycli.*, isort-sorted) import blocks."""
    client_module = f"ycli.yandex.{res.domain}.client"
    dependencies_module = f"ycli.yandex.{res.domain}.dependencies"
    models_module = f"ycli.yandex.{res.domain}.{res.resource}.models"
    models = sorted({op.response_model for op in res.operations if op.response_model})

    first_party = [
        ("ycli.yandex.models", "from ycli.yandex.models import require_found"),
        (client_module, f"from {client_module} import {domain_client_class(res)}"),
        (
            dependencies_module,
            f"from {dependencies_module} import {', '.join(_dependency_names(res))}",
        ),
        (models_module, f"from {models_module} import {', '.join(models)}"),
    ]

    lines = [
        "from fastmcp import FastMCP",
        "from fastmcp.dependencies import Depends",
        "",
    ]
    lines += [line for _module, line in sorted(first_party, key=lambda entry: entry[0])]
    return lines


def _tool(res: ir.Resource, operation: ir.Operation) -> list[str]:
    """One ``@mcp.tool``-decorated read function with a ``require_found`` empty-result guard."""
    meta = operation.mcp
    assert meta is not None  # every me operation carries an mcp facet
    guard = meta.require_found
    if guard is None:
        raise NotImplementedError("unguarded MCP tools arrive with the resource that needs them")
    annotations = f'{{**{meta.safety}, "title": "{meta.title}"}}'
    decorator = f'@mcp.tool(name="{meta.name}", annotations={annotations}, tags=TAGS)'
    parameter = f"client: {domain_client_class(res)} = Depends({res.domain}_client)"
    signature = f"def {operation.name}({parameter}) -> {operation.response_model}:"
    guard_return = (
        "    return require_found("
        f"result, sentinel=lambda r: {guard.sentinel}, "
        f'message="{guard.message}")'
    )
    return [
        decorator,
        signature,
        f'    """{meta.documentation}"""',
        f"    result = client.{res.resource}.{operation.name}()",
        guard_return,
    ]


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
