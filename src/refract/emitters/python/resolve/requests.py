from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import Import
from refract.emitters.python.resolve._common import (
    render_imports,
    signature_and_call,
    signature_params,
)
from refract.emitters.python.views import RequestsPageView

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.ports import DocComments, EmitContext, Naming, TypeMapper


def path_expr(path: str, params: tuple[ir.Param, ...], naming: Naming) -> str:
    """Emit an f-string when the path has `{placeholders}`, else a plain string literal.

    A path placeholder names its path param verbatim (`widget/{id}`); a shadowed name is rewritten
    to the guarded identifier (`{id}` -> `{id_}`) so the f-string references the safe local var. The
    substituted URL value is unchanged (a placeholder rename, not a wire change). Query params are
    never in the path, so they are not considered here.
    """
    if "{" not in path:
        return f'"{path}"'
    for param in params:
        if param.loc == "path":
            safe = naming.safe_param(param.name)
            if safe != param.name:
                path = path.replace(f"{{{param.name}}}", f"{{{safe}}}")
    return f'f"{path}"'


def _request_doc(op: ir.Operation, *, write: bool) -> str:
    if write:
        return f"``{op.method} /{op.path}`` - {op.name} request from a typed body."
    return f"``{op.method} /{op.path}`` -> {op.response_model} request builder."


def _request_function(
    op: ir.Operation, naming: Naming, type_mapper: TypeMapper, doc_comments: DocComments
) -> tuple[str, list[Import]]:
    body = op.body  # write iff not None; narrowed to ir.Body below
    positional, keyword_only, _call_args, param_imports = signature_and_call(
        op, type_mapper, naming
    )
    imports: list[Import] = list(param_imports)
    if body is not None:  # write: `body: <model>` already in `positional`; add its `.models` import
        imports.append(Import(".models", body.model))
    params = signature_params(positional, keyword_only)
    response_model = op.response_model
    if response_model is None:  # bodyless op (204/201) -> Request[None], no response import
        return_type, response_kwarg = "None", "response_model=None"
    else:
        imports.append(Import(".models", response_model))
        return_type, response_kwarg = response_model, f"response_model={response_model}"
    function_name = naming.module_function(op.name)
    param_list = ", ".join(params)
    sig = f"def {function_name}({param_list}) -> Request[{return_type}]:"

    kwargs = [f'method="{op.method}"', f"path={path_expr(op.path, op.params, naming)}"]
    query_items = [
        f'"{p.alias or p.name}": {naming.safe_param(p.name)}' for p in op.params if p.loc == "query"
    ]
    if query_items:
        kwargs.append("query={" + ", ".join(query_items) + "}")
    if body is not None:  # render model_dump flags straight off ir.Body (no .dump)
        kwargs.append(
            f"json_body=body.model_dump(by_alias={body.by_alias}, exclude_none={body.omit_none})"
        )
    kwargs.append(response_kwarg)

    doc = doc_comments.render(_request_doc(op, write=body is not None), "    ")
    lines = [sig, *doc, f"    return Request({', '.join(kwargs)})"]
    return "\n".join(lines), imports


def resolve_requests(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    doc_comments: DocComments,
) -> RequestsPageView:
    imports: list[Import] = [Import(f"{ctx.package_root}.runtime", "Request")]
    functions: list[str] = []
    for op in res.operations:
        text, fimports = _request_function(op, naming, type_mapper, doc_comments)
        functions.append(text)
        imports += fimports
    module_doc = res.module_docs.requests or (
        f"Request builders for {res.domain_title} {res.resource} - "
        "the single HTTP contract (sans-I/O)."
    )
    return RequestsPageView(
        doc_block=doc_comments.render(module_doc, ""),
        import_lines=render_imports(tuple(imports)),
        functions=tuple(functions),
    )
