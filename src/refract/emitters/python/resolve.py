from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING

from refract.emitters.api import Import
from refract.emitters.python.views import ClientPageView, RequestsPageView

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.api import Docstrings, EmitContext, Naming, TypeMapper


def render_imports(imports: tuple[Import, ...]) -> tuple[str, ...]:
    """Union -> group-by-module -> merge names -> `from <module> import <names>` (ruff orders)."""
    by_module: dict[str, set[str]] = defaultdict(set)
    for imp in imports:
        by_module[imp.module].add(imp.name)
    return tuple(
        f"from {module} import {', '.join(sorted(names))}" for module, names in by_module.items()
    )


def signature_params(positional: tuple[str, ...], keyword_only: tuple[str, ...]) -> tuple[str, ...]:
    """Assemble a param list, inserting the `*` marker before the first keyword-only param."""
    if keyword_only:
        return (*positional, "*", *keyword_only)
    return positional


def indent_lines(lines: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    """Prefix every non-blank line (blank lines stay empty)."""
    return tuple(f"{prefix}{line}" if line else "" for line in lines)


def param_decl(param: ir.Param, type_mapper: TypeMapper) -> tuple[str, tuple[Import, ...]]:
    """Render one parameter declaration `name: Type` (+ ` = default`) and its imports."""
    rt = type_mapper.render(param.type, optional=param.optional)
    default = param.default if param.default is not None else type_mapper.null_default(
        param.type, optional=param.optional
    )
    decl = f"{param.name}: {rt.text}"
    if default is not None:
        decl = f"{decl} = {default}"
    return decl, rt.imports


def path_expr(path: str) -> str:
    """Emit an f-string when the path has `{placeholders}`, else a plain string literal."""
    return f'f"{path}"' if "{" in path else f'"{path}"'


def _request_doc(op: ir.Operation, *, write: bool) -> str:
    if write:
        return f"``{op.method} /{op.path}`` - {op.name} request from a typed body."
    return f"``{op.method} /{op.path}`` -> {op.response_model} request builder."


def _request_function(
    op: ir.Operation, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings
) -> tuple[str, list[Import]]:
    body = op.body                       # write iff not None; narrowed to ir.Body below
    imports: list[Import] = []
    positional: list[str] = []
    for p in op.params:
        if p.loc == "path":
            decl, imp = param_decl(p, type_mapper)
            positional.append(decl)
            imports += imp
    if body is not None:                 # write: typed body positional + `.models` import
        positional.append(f"body: {body.model}")
        imports.append(Import(".models", body.model))
    keyword_only: list[str] = []
    for p in op.params:
        if p.loc == "query":
            decl, imp = param_decl(p, type_mapper)
            keyword_only.append(decl)
            imports += imp
    params = signature_params(tuple(positional), tuple(keyword_only))
    response_model = op.response_model
    if response_model is None:  # 204/no-body ops aren't in the walking skeleton yet - fail loud
        raise ValueError(f"{op.name}: operation has no response model (not yet supported)")
    imports.append(Import(".models", response_model))
    function_name = naming.module_function(op.name)
    param_list = ", ".join(params)
    sig = f"def {function_name}({param_list}) -> Request[{response_model}]:"

    kwargs = [f'method="{op.method}"', f"path={path_expr(op.path)}"]
    query_items = [f'"{p.alias or p.name}": {p.name}' for p in op.params if p.loc == "query"]
    if query_items:
        kwargs.append("query={" + ", ".join(query_items) + "}")
    if body is not None:                 # render model_dump flags straight off ir.Body (no .dump)
        kwargs.append(
            f"json_body=body.model_dump(by_alias={body.by_alias}, exclude_none={body.omit_none})"
        )
    kwargs.append(f"response_model={response_model}")

    doc = docstrings.render(_request_doc(op, write=body is not None), "    ")
    lines = [sig, *doc, f"    return Request({', '.join(kwargs)})"]
    return "\n".join(lines), imports


def resolve_requests(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> RequestsPageView:
    imports: list[Import] = [Import(f"{ctx.package_root}.runtime", "Request")]
    functions: list[str] = []
    for op in res.operations:
        text, fimports = _request_function(op, naming, type_mapper, docstrings)
        functions.append(text)
        imports += fimports
    module_doc = res.module_docs.requests or (
        f"Request builders for {res.domain_title} {res.resource} - "
        "the single HTTP contract (sans-I/O)."
    )
    return RequestsPageView(
        doc_block=docstrings.render(module_doc, ""),
        import_lines=render_imports(tuple(imports)),
        functions=tuple(functions),
    )


def _client_method(
    op: ir.Operation, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings
) -> tuple[str, list[Import]]:
    """One thin-sugar method leaf: `<op.name>` -> `return self._session.send(_requests.<fn>(...))`.

    Built at module nesting (docstring/body at 4 spaces), then indented one level to sit inside
    the class. Method name is verbatim `op.name`; the builder call uses `module_function(op.name)`
    (the shadow guard, so `list` -> `_requests.list_`). Docstring is the FULL `op.documentation`.
    """
    body = op.body                       # write iff not None (разд. D; narrowed to ir.Body below)
    imports: list[Import] = []
    positional: list[str] = ["self"]
    call_args: list[str] = []
    for p in op.params:
        if p.loc == "path":
            decl, imp = param_decl(p, type_mapper)
            positional.append(decl)
            call_args.append(p.name)
            imports += imp
    if body is not None:                 # write: typed body positional, forwarded through unchanged
        positional.append(f"body: {body.model}")
        call_args.append("body")
        imports.append(Import(".models", body.model))
    keyword_only: list[str] = []
    for p in op.params:
        if p.loc == "query":
            decl, imp = param_decl(p, type_mapper)
            keyword_only.append(decl)
            call_args.append(f"{p.name}={p.name}")
            imports += imp
    params = signature_params(tuple(positional), tuple(keyword_only))
    response_model = op.response_model
    if response_model is None:  # 204/no-body ops aren't in the walking skeleton yet - fail loud
        raise ValueError(f"{op.name}: operation has no response model (not yet supported)")
    imports.append(Import(".models", response_model))
    sig = f"def {op.name}({', '.join(params)}) -> {response_model}:"
    call = f"_requests.{naming.module_function(op.name)}({', '.join(call_args)})"
    doc = docstrings.render(op.documentation, "    ")
    body_lines = (sig, *doc, f"    return self._session.send({call})")
    return "\n".join(indent_lines(body_lines, "    ")), imports


def resolve_client(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> ClientPageView:
    base_class = naming.class_name(res.domain, "Resource")
    imports: list[Import] = [
        Import(f"{ctx.package_root}.base", base_class),
        Import(".", "_requests"),
    ]
    methods: list[str] = []
    for op in res.operations:
        text, method_imports = _client_method(op, naming, type_mapper, docstrings)
        methods.append(text)
        imports += method_imports
    return ClientPageView(
        doc_block=docstrings.render(res.module_docs.client, ""),
        import_lines=render_imports(tuple(imports)),
        class_header=f"class {naming.class_name(res.resource, 'Client')}({base_class}):",
        class_doc_lines=docstrings.render(res.module_docs.client_class, "    "),
        methods=tuple(methods),
    )
