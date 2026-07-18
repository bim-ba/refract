from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import Import
from refract.emitters.python.resolve._common import (
    _shared_models_module,
    py_str,
    render_imports,
    signature_and_call,
)
from refract.emitters.python.views import McpPageView
from refract.ir import Safety

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.api import Docstrings, EmitContext, Naming, TypeMapper


def _tags_symbol(safety: Safety) -> str:
    """The tags constant for a safety class (reads: ``TAGS``; writes: ``WRITE_TAGS``)."""
    return "TAGS" if safety is Safety.RO else "WRITE_TAGS"


def _mcp_signature(
    res: ir.Resource, op: ir.Operation, naming: Naming, type_mapper: TypeMapper
) -> tuple[list[str], list[Import]]:
    """Tool-function parameters in order: path, typed ``body``, query, then the DI client.

    Path/query go through ``param_decl`` (TypeMapper). Parameters stay flat (not keyword-only):
    fastmcp reads them as ordinary arguments."""
    positional, keyword_only, _call_args, imports = signature_and_call(op, type_mapper, naming)
    parameters = [
        *positional,
        *keyword_only,
        f"client: {naming.class_name(res.domain, 'Client')} = Depends({res.domain}_client)",
    ]
    return parameters, list(imports)


def _mcp_call_args(op: ir.Operation, type_mapper: TypeMapper, naming: Naming) -> str:
    """Arguments forwarded to the client call: path, ``body``, then keyword query."""
    _positional, _keyword_only, call_args, _imports = signature_and_call(op, type_mapper, naming)
    return ", ".join(call_args)


def _mcp_tool(
    res: ir.Resource,
    op: ir.Operation,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> tuple[str, list[Import]]:
    """The finished text for one ``@mcp.tool`` function, forwarding into the client (with a
    guard when ``require_found`` is declared).

    The def name is ``naming.module_function`` (``list`` -> ``list_``). The safety symbol goes
    into the generated code as ``meta.safety.value`` (the raw ``"RO"``/``"WRITE"``/...). The
    guard is formatted as one logical ``require_found(...)`` call - ruff wraps it across lines."""
    meta = op.mcp
    if meta is None:  # resolve_mcp only calls this for mcp-faceted ops - fail loud if that changes
        raise ValueError(f"{op.name}: operation has no mcp facet")
    annotations = f'{{**{meta.safety.value}, "title": {py_str(meta.title)}}}'
    decorator = (
        f"@mcp.tool(name={py_str(meta.name)}, annotations={annotations}, "
        f"tags={_tags_symbol(meta.safety)})"
    )
    parameters, imports = _mcp_signature(res, op, naming, type_mapper)
    signature = (
        f"def {naming.module_function(op.name)}({', '.join(parameters)}) "
        f"-> {op.response_model or 'None'}:"
    )
    call = f"client.{res.resource}.{op.name}({_mcp_call_args(op, type_mapper, naming)})"
    guard = meta.require_found
    if guard is None:
        body = [f"    return {call}"]
    else:
        body = [
            f"    result = {call}",
            "    return require_found("
            f"result, sentinel=lambda r: {guard.sentinel}, "
            f"message={py_str(guard.message)})",
        ]
    lines = [decorator, signature, *docstrings.render(meta.documentation, "    "), *body]
    return "\n".join(lines), imports


def resolve_mcp(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> McpPageView:
    """IR -> McpPageView: module docstring, imports (fastmcp + package_root-domain modules +
    those collected from types), ``mcp = FastMCP(...)`` plus the finished tools. Iterates only
    the operations carrying an mcp facet. ``meta.safety.value`` is the raw safety-symbol name
    (StrEnum -> str) used for the ``dependencies`` import."""
    dependencies_module = f"{ctx.package_root}.dependencies"
    models_module = f"{ctx.package_root}.{res.resource}.models"
    imports: list[Import] = [
        Import("fastmcp", "FastMCP"),
        Import("fastmcp.dependencies", "Depends"),
        Import(f"{ctx.package_root}.client", naming.class_name(res.domain, "Client")),
        Import(dependencies_module, f"{res.domain}_client"),
    ]
    tools: list[str] = []
    for op in res.operations:
        meta = op.mcp
        if meta is None:
            continue
        imports.append(Import(dependencies_module, meta.safety.value))
        imports.append(Import(dependencies_module, _tags_symbol(meta.safety)))
        if op.response_model:
            imports.append(Import(models_module, op.response_model))
        if op.body is not None:
            imports.append(Import(models_module, op.body.model))
        if meta.require_found is not None:
            imports.append(Import(_shared_models_module(ctx), "require_found"))
        text, tool_imports = _mcp_tool(res, op, naming, type_mapper, docstrings)
        tools.append(text)
        imports += tool_imports
    return McpPageView(
        doc_block=docstrings.render(res.module_docs.mcp, ""),
        import_lines=render_imports(tuple(imports)),
        server_line=f'mcp = FastMCP("{res.module_docs.mcp_server}")',
        tools=tuple(tools),
    )
