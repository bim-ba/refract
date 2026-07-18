from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from refract.emitters.api import Import
from refract.emitters.python.resolve._common import param_decl, py_str, render_imports
from refract.emitters.python.views import CliPageView
from refract.ir import ListType, MapType, ObjectModel, RefType, ScalarType
from refract.spec import SpecError

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.api import Docstrings, EmitContext, Naming, TypeMapper

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
    all_decls = [*option_decls, *path_decls, *query_decls]
    # `_assembled_options` dedups the body options internally, but a body option can still collide
    # with a path/query param name - both land in the same command signature, and two same-named
    # parameters are a duplicate-argument SyntaxError. Reject across all sources at the cause (a
    # decl is `name: type[ = default]`, so the name is the token before the first colon).
    _reject_duplicate_options(op, [decl.split(":", 1)[0].strip() for decl in all_decls])
    no_default, with_default = _partition_by_default(all_decls)
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
    """The unsupported-body-shape message - single source so both reject arms match byte-for-byte.
    Names the Q1 ``handler:`` escape as the planned mechanism, but states plainly that it is not yet
    wired: no emitter reads ``op.handler`` today, so the message must not imply setting it works."""
    return (
        f"{op.name}: body field {field.name!r} needs a handler (not yet implemented) - "
        "Assembled-CLI covers scalar + one-level ref only"
    )


def _require_object_model(op: ir.Operation, model: ir.Model) -> ObjectModel:
    """Narrow a body/ref-target ``Model`` to ``ObjectModel`` - fail loud (not a bare ``assert``,
    which ``python -O`` strips) when it names a ``RootListModel`` instead."""
    if not isinstance(model, ObjectModel):
        raise SpecError(
            f"{op.name}: body model {model.name!r} is not an object - "
            "needs a handler (not yet implemented)"
        )
    return model


def _reject_duplicate_options(op: ir.Operation, option_names: list[str]) -> None:
    """Fail loud on a repeated flat parameter name - a scalar field literally named
    ``<reffield>_<child>`` colliding with a flattened nested option (within the body), OR a body
    option colliding with a path/query param name (across sources). Two same-named parameters
    would otherwise emit a duplicate-argument ``SyntaxError`` in the generated command, silently."""
    seen: set[str] = set()
    for name in option_names:
        if name in seen:
            raise SpecError(
                f"{op.name}: CLI parameter name collision on {name!r} - "
                "rename the colliding field or param"
            )
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
    (the ``handler:`` escape is planned but not yet wired into any emitter).

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
