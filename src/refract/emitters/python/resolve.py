from __future__ import annotations

import json
from collections import defaultdict
from typing import TYPE_CHECKING, assert_never

from refract.emitters.api import Import
from refract.emitters.python.views import (
    ClientPageView,
    CliPageView,
    McpPageView,
    ModelsPageView,
    RequestsPageView,
    RootClientPageView,
    TestsPageView,
)
from refract.ir import (
    HeaderAuth,
    ListType,
    MapType,
    MultiHeaderAuth,
    ObjectModel,
    RefType,
    RootListModel,
    Safety,
    ScalarType,
    TestKind,
)
from refract.spec import SpecError

# NB: `MultiHeaderAuth`/`HeaderAuth` here are the ir.auth DESCRIPTORS (AuthScheme variants) used
# for the `match` below; the generated code imports the same-named httpx mechanisms from
# `.runtime.auth` - the resolver only ever emits the mechanism's string name.

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


def param_decl(
    param: ir.Param, type_mapper: TypeMapper, naming: Naming
) -> tuple[str, tuple[Import, ...]]:
    """Render one parameter declaration `name: Type` (+ ` = default`) and its imports.

    The declared identifier is shadow-guarded (`id` -> `id_`); the wire name (path placeholder,
    query alias/key) is preserved by the CALLER, not here."""
    rt = type_mapper.render(param.type, optional=param.optional)
    default = (
        param.default
        if param.default is not None
        else type_mapper.null_default(param.type, optional=param.optional)
    )
    decl = f"{naming.safe_param(param.name)}: {rt.text}"
    if default is not None:
        decl = f"{decl} = {default}"
    return decl, rt.imports


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


def py_str(value: str) -> str:
    """A safely-quoted Python string literal for free text (escapes quotes/backslashes/newlines).

    Uses json.dumps: double-quoted with proper escaping, matching the backend's double-quote
    style, so a quote-free value renders exactly as a hand-written "..." literal (ruff format is
    a no-op on it). ``ensure_ascii=False`` keeps non-ASCII text (em-dashes, Cyrillic, ...) literal
    instead of ``\\uXXXX`` escapes - both are valid Python, but literal matches the prior
    hand-quoted output byte-for-byte.
    """
    return json.dumps(value, ensure_ascii=False)


def signature_and_call(
    op: ir.Operation, type_mapper: TypeMapper, naming: Naming
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], tuple[Import, ...]]:
    """(positional_decls, keyword_only_decls, call_args, param_type_imports).

    positional_decls = path-param decls (+ `body: <model>` when op.body); keyword_only_decls =
    query-param decls; call_args = path names (+ "body") + `name=name` for query. imports carries
    ONLY the param TYPE imports (from param_decl). Callers add their own prefix (`self`), suffix
    (`client=Depends(...)`), the `*` marker, the response/body MODEL imports (whose module differs
    per caller), and - for requests - the alias-keyed query dict.
    """
    positional: list[str] = []
    call_args: list[str] = []
    imports: list[Import] = []
    for p in op.params:
        if p.loc == "path":
            decl, imp = param_decl(p, type_mapper, naming)
            positional.append(decl)
            call_args.append(naming.safe_param(p.name))
            imports += imp
    if op.body is not None:
        positional.append(f"body: {op.body.model}")
        call_args.append("body")
    keyword_only: list[str] = []
    for p in op.params:
        if p.loc == "query":
            decl, imp = param_decl(p, type_mapper, naming)
            keyword_only.append(decl)
            call_args.append(f"{naming.safe_param(p.name)}={naming.safe_param(p.name)}")
            imports += imp
    return tuple(positional), tuple(keyword_only), tuple(call_args), tuple(imports)


def _request_doc(op: ir.Operation, *, write: bool) -> str:
    if write:
        return f"``{op.method} /{op.path}`` - {op.name} request from a typed body."
    return f"``{op.method} /{op.path}`` -> {op.response_model} request builder."


def _request_function(
    op: ir.Operation, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings
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
    body = op.body  # write iff not None (narrowed to ir.Body below)
    positional, keyword_only, call_args, param_imports = signature_and_call(op, type_mapper, naming)
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


def _shared_models_module(ctx: EmitContext) -> str:
    """The shared base module (``APIModel``/``require_found``) - one level above the domain.

    ``ycli.yandex.tracker`` -> ``ycli.yandex.models`` (derived, not hardcoded)."""
    return f"{ctx.package_root.rsplit('.', 1)[0]}.models"


def _model_field(field: ir.Field, type_mapper: TypeMapper) -> tuple[str, list[Import]]:
    """One model field line: ``name: Type = default`` or ``Field(...)`` for a described/aliased
    field.

    The type renders from NeutralType via TypeMapper (the key port shift); the default is the
    explicit ``field.default`` or, absent that, ``type_mapper.null_default(...)`` (implied-null).
    A described or aliased field renders ``Field(...)``: optional carries ``default=<default>``
    first, then ``alias=`` (if set), then ``description=`` (if set). Long calls stay one line -
    ruff wraps them.
    """
    rendered = type_mapper.render(field.type, optional=field.optional)
    imports = list(rendered.imports)
    default = (
        field.default
        if field.default is not None
        else type_mapper.null_default(field.type, optional=field.optional)
    )
    if not field.description and not field.alias:
        return f"    {field.name}: {rendered.text} = {default}", imports
    arguments: list[str] = []
    if default is not None:
        arguments.append(f"default={default}")
    if field.alias is not None:
        arguments.append(f"alias={py_str(field.alias)}")
    if field.description is not None:
        arguments.append(f"description={py_str(field.description)}")
    return f"    {field.name}: {rendered.text} = Field({', '.join(arguments)})", imports


def _model_class(
    model: ir.Model, type_mapper: TypeMapper, docstrings: Docstrings
) -> tuple[str, list[Import]]:
    """The finished source for one model class - dispatches over the ``Model`` union.

    ``RootListModel`` -> ``RootModel[list[Item]]`` with just a docstring; ``ObjectModel`` ->
    docstring, blank line, then fields. ``model.item`` is the model name (a str, not a
    NeutralType) and renders verbatim. ``assert_never`` keeps the union exhaustive - a new
    variant is a type error, not a silent no-op.
    """
    match model:
        case RootListModel():
            lines = [
                f"class {model.name}(RootModel[list[{model.item}]]):",
                *docstrings.render(model.documentation, "    "),
            ]
            return "\n".join(lines), []
        case ObjectModel():
            lines = [f"class {model.name}(APIModel):"]
            lines += docstrings.render(model.documentation, "    ")
            lines.append("")
            imports: list[Import] = []
            for field in model.fields:
                decl, field_imports = _model_field(field, type_mapper)
                lines.append(decl)
                imports += field_imports
            return "\n".join(lines), imports
        case _:
            assert_never(model)


def resolve_models(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> ModelsPageView:
    """IR -> ModelsPageView: module docstring, imports (APIModel + pydantic + those collected
    from types), finished classes. ``APIModel`` is always imported."""
    imports: list[Import] = [Import(_shared_models_module(ctx), "APIModel")]
    if any(
        field.description or field.alias
        for model in res.models
        if isinstance(model, ObjectModel)
        for field in model.fields
    ):
        imports.append(Import("pydantic", "Field"))
    if any(isinstance(model, RootListModel) for model in res.models):
        imports.append(Import("pydantic", "RootModel"))
    classes: list[str] = []
    for model in res.models:
        text, class_imports = _model_class(model, type_mapper, docstrings)
        classes.append(text)
        imports += class_imports
    return ModelsPageView(
        doc_block=docstrings.render(res.module_docs.models, ""),
        header_lines=("from __future__ import annotations",),
        import_lines=render_imports(tuple(imports)),
        classes=tuple(classes),
    )


_GROUP_DOC = "Group anchor - forces subcommand dispatch (no eager DI, so --help stays cred-free)."


def _remap_to_resource_models(
    ctx: EmitContext, res: ir.Resource, imports: list[Import]
) -> list[Import]:
    """Rewrite each ``.models`` relative import to the resource's ABSOLUTE models module.

    ``_assembled_options`` mirrors requests/client with ``Import(".models", X)``, but inside the
    generated cli package (``ycli.cli``) ``.models`` resolves to ``ycli.cli.models`` - wrong. The
    absolute target is the same one ``resolve_mcp`` uses: ``<package_root>.<resource>.models``.
    Non-``.models`` imports (path/query scalar types) pass through untouched.
    """
    models_module = f"{ctx.package_root}.{res.resource}.models"
    return [Import(models_module, imp.name) if imp.module == ".models" else imp for imp in imports]


def _partition_by_default(decls: list[str]) -> tuple[list[str], list[str]]:
    """Split param decls into ``(no_default, with_default)``, preserving relative order in each.

    A decl carries a default iff it contains ``" = "``: ``param_decl``/``_option_decl`` render a
    default as literally `` = <expr>`` appended to the type text, and a bare type annotation
    (``str``, ``str | None``, ``list[str]``, ...) never contains ``" = "`` on its own - so the
    substring test is a safe, cheap proxy for "was this decl built with a default value".
    """
    no_default = [decl for decl in decls if " = " not in decl]
    with_default = [decl for decl in decls if " = " in decl]
    return no_default, with_default


def _cli_write_parts(
    res: ir.Resource, op: ir.Operation, ctx: EmitContext, naming: Naming, type_mapper: TypeMapper
) -> tuple[str, str, list[Import]]:
    """``(signature_tail, call_args, imports)`` for one write command.

    ``signature_tail`` is the suffix rendered after ``ctx``: every decl WITHOUT a default (options,
    path, query - in that source order), then every decl WITH a default, each group preserving its
    relative order (``_partition_by_default``). Plain source-order concatenation can put a
    required param (e.g. a path param) after a defaulted one (e.g. an optional body option),
    which Python rejects with a ``SyntaxError``; partitioning both fixes that and gives sensible
    typer semantics (required -> positional Arguments first, optional -> Options after).
    ``call_args`` forwards path names (positional), the reassembled body expr, then ``name=name``
    query kwargs - matching the client method's ``(path, body, *, query)`` order, independent of
    how the command signature above is ordered. Imports are the body/ref model imports (remapped
    from relative ``.models`` to the resource's absolute module) plus path/query scalar-type
    imports.
    """
    option_decls, reassembly_expr, model_imports = _assembled_options(res, op, type_mapper, naming)
    path_decls: list[str] = []
    path_names: list[str] = []
    query_decls: list[str] = []
    query_kwargs: list[str] = []
    param_imports: list[Import] = []
    for param in op.params:
        decl, decl_imports = param_decl(param, type_mapper, naming)
        param_imports += decl_imports
        safe = naming.safe_param(param.name)  # the guarded local identifier forwarded to the client
        if param.loc == "path":
            path_decls.append(decl)
            path_names.append(safe)
        else:  # query
            query_decls.append(decl)
            query_kwargs.append(f"{safe}={safe}")
    no_default, with_default = _partition_by_default([*option_decls, *path_decls, *query_decls])
    signature_tail = "".join(f", {decl}" for decl in (*no_default, *with_default))
    call_args = ", ".join((*path_names, reassembly_expr, *query_kwargs))
    imports = _remap_to_resource_models(ctx, res, [*model_imports, *param_imports])
    return signature_tail, call_args, imports


def _cli_command(
    res: ir.Resource,
    op: ir.Operation,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> tuple[str, list[Import]]:
    """The finished text (+ model imports) for one ``@app.command()`` leaf.

    A READ op (no body) stays the param-less passthrough (byte-identical to the `me` emitter):
    resolves ``AppContext`` and forwards ``app_ctx.<domain>.<resource>.<op>()`` through
    ``Serializer.serialize``, pulling no imports. A WRITE op (``op.body``) carries the assembled
    flat options (+ path/query params) in its signature, reassembles the typed body, and forwards
    ``app_ctx.<d>.<r>.<op>(<path>, <body>, <query>)``. The command name is author-controlled via
    ``op.cli.name`` (not necessarily ``op.name``).
    """
    meta = op.cli
    if meta is None:  # resolve_cli only calls this for cli-faceted ops - fail loud if that changes
        raise ValueError(f"{op.name}: operation has no cli facet")
    if op.body is None:  # read: param-less passthrough (unchanged)
        signature_tail, call_args, imports = "", "", []
    else:  # write: flat options -> reassembled typed body
        signature_tail, call_args, imports = _cli_write_parts(res, op, ctx, naming, type_mapper)
    call = f"app_ctx.{res.domain}.{res.resource}.{op.name}({call_args})"
    lines = [
        "@app.command()",
        f"def {meta.name}(ctx: typer.Context{signature_tail}) -> None:",
        *docstrings.render(meta.documentation, "    "),
        "    app_ctx = AppContext.from_typer_context(ctx)",
        f"    Serializer.serialize({call}, app_ctx.strategy, app_ctx.console)",
    ]
    return "\n".join(lines), imports


def resolve_cli(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> CliPageView:
    """IR -> CliPageView: module docstring, fixed imports, body = group+callback then commands."""
    group_block = "\n".join(
        [
            f'app = typer.Typer(name="{res.resource}", '
            f"help={py_str(res.module_docs.cli_group_help or '')}, no_args_is_help=True)",
            "",
            "",
            "@app.callback()",
            "def _group() -> None:",
            f'    """{_GROUP_DOC}"""',
        ]
    )
    blocks = [group_block]
    command_imports: list[Import] = []
    for op in res.operations:
        if op.cli is not None:
            text, cmd_imports = _cli_command(res, op, ctx, naming, type_mapper, docstrings)
            blocks.append(text)
            command_imports += cmd_imports
    return CliPageView(
        doc_block=docstrings.render(res.module_docs.cli, ""),
        header_lines=("from __future__ import annotations",),
        import_lines=(
            "import typer",
            *render_imports(
                (
                    Import("ycli.cli.context", "AppContext"),
                    Import("ycli.cli.output", "Serializer"),
                    *command_imports,
                )
            ),
        ),
        blocks=tuple(blocks),
    )


def _option_decl(
    name: str, field: ir.Field, type_mapper: TypeMapper
) -> tuple[str, tuple[Import, ...]]:
    """One typer option decl ``name: Type`` (+ `` = default``) for a body ``Field``.

    Mirrors ``param_decl`` (a typer option IS a parameter), but takes an explicit ``name`` so a
    nested field can flatten to ``<parent>_<child>``. Default is the field's explicit spec default
    or, absent that, ``type_mapper.null_default`` (implied-null).
    """
    rendered = type_mapper.render(field.type, optional=field.optional)
    default = (
        field.default
        if field.default is not None
        else type_mapper.null_default(field.type, optional=field.optional)
    )
    decl = f"{name}: {rendered.text}"
    if default is not None:
        decl = f"{decl} = {default}"
    return decl, rendered.imports


def _handler_hint(op: ir.Operation, field: ir.Field) -> str:
    """The Q1 escape-hatch message - single source so both reject arms match byte-for-byte."""
    return (
        f"{op.name}: body field {field.name!r} needs handler: "
        "(Assembled-CLI covers scalar + one-level ref)"
    )


def _require_object_model(op: ir.Operation, model: ir.Model) -> ObjectModel:
    """Narrow a body/ref-target ``Model`` to ``ObjectModel`` - fail loud (not a bare ``assert``,
    which ``python -O`` strips) when it names a ``RootListModel`` instead."""
    if not isinstance(model, ObjectModel):
        raise SpecError(f"{op.name}: body model {model.name!r} is not an object (needs handler:)")
    return model


def _reject_duplicate_options(op: ir.Operation, option_names: list[str]) -> None:
    """Fail loud on a repeated flat option name (e.g. a scalar field literally named
    ``<reffield>_<child>`` colliding with a flattened nested option) - two same-named typer
    params would otherwise emit a ``SyntaxError`` in the generated code, silently."""
    seen: set[str] = set()
    for name in option_names:
        if name in seen:
            raise SpecError(f"{op.name}: CLI option name collision on {name!r} - needs handler:")
        seen.add(name)


def _assembled_options(
    res: ir.Resource, op: ir.Operation, type_mapper: TypeMapper, naming: Naming
) -> tuple[list[str], str, list[Import]]:
    """Flatten a write op's body model into flat typer options + a body-reassembly expression.

    Walk ``res.model(op.body.model)`` (an ObjectModel) one level: a scalar field -> one option
    ``name: Type`` reassembled ``name=name``; a one-level ``ref<Target>`` field fans Target's
    scalar fields into ``<parent>_<child>`` options reassembled
    ``parent=Target(child=<parent>_<child>, ...)``. Any shape past scalar + one-level-ref (map,
    list, a ref nested two levels down) is the Q1 escape hatch - a ``SpecError`` naming the field
    and suggesting a ``handler:``.

    Returns ``(option_decls, reassembly_expr, imports)``. For a PriorityCreate {key, name:
    ref<LocalizedName>{ru?, en?}, order?, description?} body the expr is exactly
    ``PriorityCreate(key=key, name=LocalizedName(ru=name_ru, en=name_en), order=order,
    description=description)``.
    """
    body = op.body
    if body is None:  # write-op only; a bodyless op reaching here is a wiring bug - fail loud
        raise ValueError(f"{op.name}: assembled options require a write body")
    model = _require_object_model(op, res.model(body.model))
    # Shape-aligned with `_body_test_imports`: both walk the body model's one-level `ref<...>`
    # fields (third consumer -> extract a shared walker). Imports open with the body model (the
    # reassembly ctor); `.models` mirrors requests/client - the CLI wiring (D5b) supplies the
    # final module.
    option_decls: list[str] = []
    option_names: list[str] = []
    reassembly: list[str] = []
    imports: list[Import] = [Import(".models", body.model)]
    for field in model.fields:
        match field.type:
            case ScalarType():
                option_name = naming.safe_param(field.name)  # guarded typer option identifier
                decl, decl_imports = _option_decl(option_name, field, type_mapper)
                option_decls.append(decl)
                option_names.append(option_name)
                imports += decl_imports
                reassembly.append(f"{field.name}={option_name}")  # KWARG=field name; VALUE=guarded
            case RefType(target=target):
                nested = _require_object_model(op, res.model(target))
                inner: list[str] = []
                for child in nested.fields:
                    match child.type:
                        case ScalarType():
                            option_name = naming.safe_param(
                                naming.cli_option(field.name, child.name)
                            )
                            decl, decl_imports = _option_decl(option_name, child, type_mapper)
                            option_decls.append(decl)
                            option_names.append(option_name)
                            imports += decl_imports
                            inner.append(f"{child.name}={option_name}")
                        case RefType() | ListType() | MapType():  # two-level nest -> escape hatch
                            raise SpecError(_handler_hint(op, field))
                        case _:  # closed union (ir/types.py) - unreachable, not a real arm
                            assert_never(child.type)
                imports.append(Import(".models", target))
                reassembly.append(f"{field.name}={target}({', '.join(inner)})")
            case ListType() | MapType():  # not flattenable to scalar leaves
                raise SpecError(_handler_hint(op, field))
            case _:  # closed union (ir/types.py) - unreachable, not a real arm
                assert_never(field.type)
    _reject_duplicate_options(op, option_names)
    return option_decls, f"{body.model}({', '.join(reassembly)})", imports


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


# Docstring for the require_found empty-response guard (structural - only the 200-empty case,
# tied to the sentinel ``r.login is None`` declared by the read-tool).
_EMPTY_GUARD_DOC = (
    "200 with empty body hits the login-is-None guard (e.g. bad permissions -> blank object)."
)


def _tests_module_doc(res: ir.Resource, ops: tuple[ir.Operation, ...], kinds: set[TestKind]) -> str:
    """Text of the test-module docstring: ``<Domain> /<path[+path...]> resource - <surfaces>,
    HTTP stubbed.`` Path segments are the UNIQUE ``op.path`` values across all tests-bearing ops,
    joined with `` + `` - byte-identical to the prior single-op form when only one op qualifies.
    """
    labels = []
    if TestKind.CLIENT in kinds:
        labels.append("client")
    if TestKind.CLI in kinds:
        labels.append("CLI")
    if kinds & {TestKind.MCP, TestKind.MCP_GUARD}:
        labels.append("MCP")
    surfaces = " + ".join(labels)
    paths = " + ".join(dict.fromkeys(op.path for op in ops))
    return f"{res.domain_title} /{paths} resource - {surfaces}, HTTP stubbed."


def _body_test_imports(res: ir.Resource, body: ir.Body, models_module: str) -> tuple[Import, ...]:
    """The body model's import, plus any of its directly-nested ``ref<...>`` fields.

    A CLIENT-kind test's authored ``call`` constructs the body model literally in Python (e.g.
    ``PriorityCreate(name=LocalizedName(...))``), so a nested ref field needs its own import too -
    one level deep only (no write body in this codebase nests a ref two levels down yet).
    """
    model = res.model(body.model)
    imports = [Import(models_module, body.model)]
    if isinstance(model, ObjectModel):
        imports += [
            Import(models_module, field.type.target)
            for field in model.fields
            if isinstance(field.type, RefType)
        ]
    return tuple(imports)


def _tests_imports(
    res: ir.Resource,
    ops: tuple[ir.Operation, ...],
    ctx: EmitContext,
    kinds: set[TestKind],
    client_class: str,
) -> tuple[str, ...]:
    has_client = TestKind.CLIENT in kinds
    has_cli = TestKind.CLI in kinds
    has_mcp = TestKind.MCP in kinds
    has_mcp_guard = TestKind.MCP_GUARD in kinds

    stdlib: list[str] = []
    if has_mcp:
        stdlib.append("import asyncio")
    if has_cli:
        stdlib.append("import json")

    third_party: list[str] = []
    if has_mcp_guard:
        third_party.append("import pytest")
    third_party.append("import responses")
    if has_mcp or has_mcp_guard:
        third_party.append("from fastmcp import Client")
    if has_mcp_guard:
        third_party.append("from fastmcp.exceptions import ToolError")
    if has_cli:
        third_party.append("from typer.testing import CliRunner")

    first_party: list[str] = []
    if has_cli:
        first_party.append("import ycli.cli.app as cli")
    if has_mcp:
        first_party.append("from ycli.mcp import mcp as root_mcp")
    if has_client:
        first_party.append(f"from {ctx.package_root}.client import {client_class}")
    if has_mcp_guard:
        first_party.append(
            f"from {ctx.package_root}.{res.resource} import mcp as {res.resource}_mcp_module"
        )
    models_module = f"{ctx.package_root}.{res.resource}.models"
    model_imports: list[Import] = []
    for op in ops:
        has_client_case = any(case.kind is TestKind.CLIENT for case in op.tests)
        if has_client_case and op.response_model:
            model_imports.append(Import(models_module, op.response_model))
        if has_client_case and op.body is not None:
            model_imports.extend(_body_test_imports(res, op.body, models_module))
    first_party.extend(render_imports(tuple(model_imports)))
    return (*stdlib, *third_party, *first_party)


def _tests_constants(
    res: ir.Resource, op: ir.Operation, ctx: EmitContext, kinds: set[TestKind]
) -> tuple[str, ...]:
    """Module constants: ``_URL_<op.name>`` (always), ``_PAYLOAD_<op.name>`` (client case),
    ``_runner`` (cli case, shared - not op-suffixed; harmlessly re-assigned to the same value if
    more than one op has CLI tests).

    ``_URL_<op.name>`` / ``_PAYLOAD_<op.name>`` are ALWAYS per-op suffixed - one rule, applied
    even when a single op has tests - so two tests-bearing ops never collide on the same
    constant name. Built from ``ctx.config.server.base_url`` (``base_url`` left ``Resource`` for
    ``ClientConfig``). ``response_json`` is authored data; ``!r`` produces a single-quote repr,
    which ruff normalizes to double-quote. No type lowering is needed."""
    if ctx.config is None:
        raise ValueError("tests surface requires ClientConfig (base_url)")
    lines = [f'_URL_{op.name} = "{ctx.config.server.base_url}/{op.path}"']
    if TestKind.CLIENT in kinds:
        client_case = next(case for case in op.tests if case.kind is TestKind.CLIENT)
        lines.append(f"_PAYLOAD_{op.name} = {client_case.response_json!r}")
    if TestKind.CLI in kinds:
        lines.append("_runner = CliRunner()")
    return tuple(lines)


def _stub(op: ir.Operation, case: ir.TestCase) -> str:
    """The ``responses.add(...)`` line (``_PAYLOAD_<op.name>`` for reads, inline ``{}`` for guard
    cases), stubbing the per-op ``_URL_<op.name>`` constant."""
    json_arg = (
        repr(case.response_json) if case.kind is TestKind.MCP_GUARD else f"_PAYLOAD_{op.name}"
    )
    return (
        f"    responses.add(responses.{case.http_method}, _URL_{op.name}, "
        f"json={json_arg}, status={case.status})"
    )


def _asserts(case: ir.TestCase) -> list[str]:
    """One ``assert <expr>`` line per authored assert."""
    return [f"    assert {expr}" for expr in case.asserts]


def _client_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """Client case - chain the client call, then the authored asserts."""
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(op, case),
        f"    {res.resource} = {case.call}",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _cli_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """CLI case - ``CliRunner`` json-invoke of the ``<domain> <resource> <command>`` command."""
    if op.cli is None:  # resolve_tests only calls this for cli-kind cases - fail loud otherwise
        raise ValueError(f"{op.name}: operation has no cli facet")
    argv = ", ".join(
        f'"{token}"' for token in ("--format", "json", res.domain, res.resource, op.cli.name)
    )
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(op, case),
        f"    res = _runner.invoke(cli.app, [{argv}])",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _mcp_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """MCP case - call the root-composed tool through ``root_mcp`` under ``asyncio.run``."""
    if op.mcp is None:  # resolve_tests only calls this for mcp-kind cases - fail loud otherwise
        raise ValueError(f"{op.name}: operation has no mcp facet")
    root_tool = f"{res.domain}_{op.mcp.name}"
    lines = [
        "@responses.activate",
        f"def test_{case.name}(creds):",
        _stub(op, case),
        "",
        "    async def go():",
        "        async with Client(root_mcp) as client:",
        f'            return await client.call_tool("{root_tool}", {{}})',
        "",
        "    result = asyncio.run(go())",
        *_asserts(case),
    ]
    return "\n".join(lines)


def _guard_test(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """MCP guard case - the resource-local tool must raise ``ToolError`` (no asserts)."""
    if op.mcp is None:  # resolve_tests only calls this for guard cases - fail loud otherwise
        raise ValueError(f"{op.name}: operation has no mcp facet")
    lines = ["@responses.activate", f"async def test_{case.name}(creds):"]
    if case.status == 200:
        lines.append(f'    """{_EMPTY_GUARD_DOC}"""')
    lines += [
        _stub(op, case),
        f"    async with Client({res.resource}_mcp_module.mcp) as client:",
        "        with pytest.raises(ToolError):",
        f'            await client.call_tool("{op.mcp.name}", {{}})',
    ]
    return "\n".join(lines)


def _test_block(res: ir.Resource, op: ir.Operation, case: ir.TestCase) -> str:
    """Dispatch one authored ``TestCase`` to its per-kind renderer (identity on ``TestKind``)."""
    match case.kind:
        case TestKind.CLIENT:
            return _client_test(res, op, case)
        case TestKind.CLI:
            return _cli_test(res, op, case)
        case TestKind.MCP:
            return _mcp_test(res, op, case)
        case TestKind.MCP_GUARD:
            return _guard_test(res, op, case)
        case _:
            assert_never(case.kind)


def resolve_tests(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> TestsPageView:
    """IR -> TestsPageView. Iterates ALL tests-bearing operations (not just the first), unions
    their ``kinds`` (a set of ``TestKind``) to gate imports/module-doc, and renders one leaf per
    case across every such op. Constants are collected per op - ``_tests_constants`` always
    suffixes ``_URL``/``_PAYLOAD`` with ``op.name``, so only the shared, non-suffixed
    ``_runner = CliRunner()`` line could ever repeat (harmless: re-assigning the same value).
    ``type_mapper`` is unused here - all TestCase values are authored."""
    tested = tuple(operation for operation in res.operations if operation.tests)
    kinds = {case.kind for op in tested for case in op.tests}
    client_class = naming.class_name(res.domain, "Client")
    constants: list[str] = []
    tests: list[str] = []
    for op in tested:
        constants.extend(_tests_constants(res, op, ctx, {case.kind for case in op.tests}))
        tests.extend(_test_block(res, op, case) for case in op.tests)
    return TestsPageView(
        doc_block=docstrings.render(_tests_module_doc(res, tested, kinds), ""),
        header_lines=("from __future__ import annotations",),
        import_lines=_tests_imports(res, tested, ctx, kinds, client_class),
        constants=tuple(constants),
        tests=tuple(tests),
    )


def _auth_value(template: str, inputs: tuple[ir.AuthInput, ...]) -> str:
    """One header value: a bare input var for a pure ``"{name}"`` placeholder, else an f-string.

    ``"{organization_id}"`` -> ``organization_id``; ``"OAuth {oauth_token}"`` ->
    ``f"OAuth {oauth_token}"``.
    """
    for auth_input in inputs:
        if template == f"{{{auth_input.name}}}":
            return auth_input.name
    return f'f"{template}"'


def _multi_header_call(scheme: MultiHeaderAuth) -> str:
    """``MultiHeaderAuth({...})`` mechanism call from the scheme's ``(header, template)`` pairs."""
    entries = ", ".join(
        f'"{header}": {_auth_value(template, scheme.inputs)}' for header, template in scheme.headers
    )
    return f"MultiHeaderAuth({{{entries}}})"


def _header_call(scheme: HeaderAuth) -> str:
    """``HeaderAuth("<header>", <value>)`` mechanism call (single templated header)."""
    return f'HeaderAuth("{scheme.header}", {_auth_value(scheme.template, scheme.inputs)})'


def _select_scheme(config: ir.ClientConfig, security: str) -> ir.AuthScheme:
    """Index ``ClientConfig.auth`` (tuple-of-pairs) by the resource's ``security`` scheme name."""
    for name, scheme in config.auth:
        if name == security:
            return scheme
    raise SpecError(f"security {security!r} names no auth scheme in client.yaml")


def resolve_root_client(
    resources: tuple[ir.Resource, ...],
    ctx: EmitContext,
    naming: Naming,
    docstrings: Docstrings,
) -> RootClientPageView:
    """IR + ClientConfig -> RootClientPageView: the composition root. Runs once over ALL
    resources (per-API invariant: shared ``domain`` + ``security``, so read from ``resources[0]``).
    """
    if ctx.config is None:
        raise ValueError("root_client surface requires ClientConfig (server + auth)")
    domain = resources[0].domain
    client_class = naming.class_name(domain, "Client")
    scheme = _select_scheme(ctx.config, resources[0].security)
    match scheme:
        case MultiHeaderAuth():
            mechanism, auth_expr = "MultiHeaderAuth", _multi_header_call(scheme)
        case HeaderAuth():
            mechanism, auth_expr = "HeaderAuth", _header_call(scheme)
        case _:
            assert_never(scheme)

    ctor_params = signature_params(
        ("self",), tuple(f"{auth_input.name}: str" for auth_input in scheme.inputs)
    )
    init_lines = (
        f"def __init__({', '.join(ctor_params)}) -> None:",
        f"    auth = {auth_expr}",
        f'    session = Session("{ctx.config.server.base_url}", client=httpx.Client(auth=auth))',
        *(
            f"    self.{res.resource} = {naming.class_name(res.resource, 'Client')}(session)"
            for res in resources
        ),
    )
    from_env_lines = (
        "@classmethod",
        f"def from_env(cls) -> {client_class}:",
        *docstrings.render(
            "The single sanctioned env-read point (composition root); components never read env.",
            "    ",
        ),
        "    return cls(",
        *(
            f'        {auth_input.name}=os.environ["{auth_input.env}"],'
            for auth_input in scheme.inputs
        ),
        "    )",
    )
    imports = (
        "import os",
        "import httpx",
        *render_imports(
            (
                Import(".runtime.session", "Session"),
                Import(".runtime.auth", mechanism),
                *(
                    Import(f".{res.resource}.client", naming.class_name(res.resource, "Client"))
                    for res in resources
                ),
            )
        ),
    )
    title = resources[0].domain_title
    return RootClientPageView(
        doc_block=docstrings.render(
            f"{title} client - the composition root (aggregates resources, owns transport + auth).",
            "",
        ),
        header_lines=("from __future__ import annotations",),
        import_lines=imports,
        class_header=f"class {client_class}:",
        class_doc_lines=docstrings.render(f"Root client for the {title} API.", "    "),
        methods=(
            "\n".join(indent_lines(init_lines, "    ")),
            "\n".join(indent_lines(from_env_lines, "    ")),
        ),
    )
