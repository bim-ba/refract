from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import Import
from refract.emitters.python.resolve._common import (
    indent_lines,
    render_imports,
    signature_and_call,
    signature_params,
)
from refract.emitters.python.views import ClientPageView

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.ports import EmitContext


def _client_method(op: ir.Operation, ctx: EmitContext) -> tuple[str, list[Import]]:
    """One thin-sugar method leaf: `<op.name>` -> `return self._session.send(_requests.<fn>(...))`.

    Built at module nesting (docstring/body at 4 spaces), then indented one level to sit inside
    the class. Method name is verbatim `op.name`; the builder call uses `module_function(op.name)`
    (the shadow guard, so `list` -> `_requests.list_`). Docstring is the FULL `op.documentation`.
    """
    body = op.body  # write iff not None (narrowed to ir.Body below)
    positional, keyword_only, call_args, param_imports = signature_and_call(op, ctx)
    positional = ("self", *positional)
    imports: list[Import] = list(param_imports)
    if body is not None:  # write: typed body forwarded through unchanged; add its `.models` import
        imports.append(Import(".models", body.model))
    params = signature_params(positional, keyword_only)
    response_model = op.response_model
    if response_model is not None:  # bodyless op (204/201) -> `-> None`, no response import
        imports.append(Import(".models", response_model))
    return_type = response_model or "None"
    sig = f"def {op.name}({', '.join(params)}) -> {return_type}:"
    call = f"_requests.{ctx.naming.identifier(op.name)}({', '.join(call_args)})"
    doc = ctx.doc_comments.render(op.documentation, "    ")
    body_lines = (sig, *doc, f"    return self._session.send({call})")
    return "\n".join(indent_lines(body_lines, "    ")), imports


def resolve_client(res: ir.Resource, ctx: EmitContext) -> ClientPageView:
    base_class = ctx.naming.class_name(res.domain, "Resource")
    imports: list[Import] = [
        Import(f"{ctx.package_root}.base", base_class),
        Import(".", "_requests"),
    ]
    methods: list[str] = []
    for op in res.operations:
        text, method_imports = _client_method(op, ctx)
        methods.append(text)
        imports += method_imports
    return ClientPageView(
        doc_block=ctx.doc_comments.render(res.module_docs.client, ""),
        import_lines=render_imports(tuple(imports)),
        class_header=f"class {ctx.naming.class_name(res.resource, 'Client')}({base_class}):",
        class_doc_lines=ctx.doc_comments.render(res.module_docs.client_class, "    "),
        methods=tuple(methods),
    )
