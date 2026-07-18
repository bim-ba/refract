"""Task 8 (D5a): the Assembled-CLI option builder - `_assembled_options` walks a write op's body
model into flat typer options + a reassembly expression, with the Q1 escape hatch (`SpecError`
suggesting a `handler:`) for any shape past scalar + one-level ref.

Fixtures are synthetic (built in-Python, mirroring examples/ycli-tracker/.../priorities) so the
walk is exercised without loading a spec file.
"""

from __future__ import annotations

import ast

import pytest

from refract import ir
from refract.emitters.api import EmitContext
from refract.emitters.python import resolve
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.types import PythonTypeMapper
from refract.spec import SpecError

NAMING = PythonNaming()
TYPE_MAPPER = PythonTypeMapper()
DOCSTRINGS = PythonDocstrings()
CTX = EmitContext(package_root="ycli.yandex.tracker")

_STRING = ir.ScalarType(scalar="string")


def _priorities_like_resource() -> ir.Resource:
    """A PriorityCreate {key, name: ref<LocalizedName>{ru?, en?}, order?, description?} body."""
    localized_name = ir.ObjectModel(
        name="LocalizedName",
        fields=(
            ir.Field(name="ru", type=_STRING, optional=True),
            ir.Field(name="en", type=_STRING, optional=True),
        ),
    )
    priority_create = ir.ObjectModel(
        name="PriorityCreate",
        fields=(
            ir.Field(name="key", type=_STRING),
            ir.Field(name="name", type=ir.RefType(target="LocalizedName")),
            ir.Field(name="order", type=ir.ScalarType(scalar="integer"), optional=True),
            ir.Field(name="description", type=_STRING, optional=True),
        ),
    )
    create = ir.Operation(
        name="create",
        method="POST",
        path="priorities",
        operation_id="priorities_create",
        body=ir.Body(model="PriorityCreate"),
        response_model="Priority",
        cli=ir.CliMeta(name="create", documentation="Create a priority."),
    )
    return ir.Resource(
        domain="tracker",
        resource="priorities",
        security="oauth_token",
        models=(priority_create, localized_name),
        operations=(create,),
    )


def _single_body_resource(model: ir.ObjectModel) -> ir.Resource:
    """A resource whose one write op posts `model` (plus any nested models passed in `extra`)."""
    op = ir.Operation(
        name="write",
        method="POST",
        path="things",
        operation_id="things_write",
        body=ir.Body(model=model.name),
    )
    return ir.Resource(
        domain="tracker",
        resource="things",
        security="oauth_token",
        models=(model,),
        operations=(op,),
    )


def test_assembled_options_flatten_one_level_ref():
    res = _priorities_like_resource()
    op = res.operations[0]
    decls, expr, imports = resolve._assembled_options(res, op, TYPE_MAPPER, NAMING)
    joined = " ".join(decls)
    assert "key: str" in joined  # required scalar leaf - no default
    assert "name_ru: str | None" in joined  # one-level ref<LocalizedName> flattened
    assert expr == (
        "PriorityCreate(key=key, name=LocalizedName(ru=name_ru, en=name_en), "
        "order=order, description=description)"
    )
    modules = {(imp.module, imp.name) for imp in imports}
    assert (".models", "PriorityCreate") in modules  # body model (the reassembly ctor)
    assert (".models", "LocalizedName") in modules  # nested ref target


def test_assembled_options_rejects_map_body():
    labels = ir.MapType(key=_STRING, value=_STRING)
    model = ir.ObjectModel(name="Bulk", fields=(ir.Field(name="labels", type=labels),))
    res = _single_body_resource(model)
    with pytest.raises(SpecError, match="handler:"):
        resolve._assembled_options(res, res.operations[0], TYPE_MAPPER, NAMING)


def test_assembled_options_rejects_two_level_ref():
    """A ref whose target itself carries a non-scalar field cannot flatten one level."""
    mid = ir.ObjectModel(
        name="Mid",
        fields=(ir.Field(name="grid", type=ir.MapType(key=_STRING, value=_STRING)),),
    )
    outer = ir.ObjectModel(
        name="Outer", fields=(ir.Field(name="nested", type=ir.RefType(target="Mid")),)
    )
    res = ir.Resource(
        domain="tracker",
        resource="things",
        security="oauth_token",
        models=(outer, mid),
        operations=(
            ir.Operation(
                name="write",
                method="POST",
                path="things",
                operation_id="things_write",
                body=ir.Body(model="Outer"),
            ),
        ),
    )
    with pytest.raises(SpecError, match="handler:"):
        resolve._assembled_options(res, res.operations[0], TYPE_MAPPER, NAMING)


def test_assembled_options_rejects_ref_to_root_list_target():
    """A ref field targeting a `root_list` model can't be narrowed to scalar children - fail loud
    with a `SpecError` (not the bare `AssertionError` `python -O` would strip)."""
    tags = ir.RootListModel(name="Tags", item="str")
    outer = ir.ObjectModel(
        name="Outer", fields=(ir.Field(name="tags", type=ir.RefType(target="Tags")),)
    )
    res = ir.Resource(
        domain="tracker",
        resource="things",
        security="oauth_token",
        models=(outer, tags),
        operations=(
            ir.Operation(
                name="write",
                method="POST",
                path="things",
                operation_id="things_write",
                body=ir.Body(model="Outer"),
            ),
        ),
    )
    with pytest.raises(SpecError, match=r"not an object.*handler:"):
        resolve._assembled_options(res, res.operations[0], TYPE_MAPPER, NAMING)


def test_assembled_options_rejects_option_name_collision():
    """A scalar field literally named `<reffield>_<child>` collides with the flattened option
    generated for that ref field's child - two same-named typer params is a silent wiring bug
    (`SyntaxError` in the generated code), so it must fail loud instead."""
    localized_name = ir.ObjectModel(
        name="LocalizedName", fields=(ir.Field(name="ru", type=_STRING),)
    )
    model = ir.ObjectModel(
        name="Collide",
        fields=(
            ir.Field(name="name", type=ir.RefType(target="LocalizedName")),
            ir.Field(name="name_ru", type=_STRING),
        ),
    )
    op = ir.Operation(
        name="write",
        method="POST",
        path="things",
        operation_id="things_write",
        body=ir.Body(model="Collide"),
    )
    res = ir.Resource(
        domain="tracker",
        resource="things",
        security="oauth_token",
        models=(model, localized_name),
        operations=(op,),
    )
    with pytest.raises(SpecError, match="collision"):
        resolve._assembled_options(res, op, TYPE_MAPPER, NAMING)


def test_assembled_options_guards_shadowed_body_field():
    """A body field named `id` (a builtin) must emit the guarded option identifier `id_` while the
    reassembly KWARG stays the model field name -> `Widget(id=id_)` (wire/field name preserved)."""
    model = ir.ObjectModel(name="Widget", fields=(ir.Field(name="id", type=_STRING),))
    res = _single_body_resource(model)
    decls, expr, _imports = resolve._assembled_options(res, res.operations[0], TYPE_MAPPER, NAMING)
    assert "id_: str" in " ".join(decls)  # guarded typer option identifier
    assert expr == "Widget(id=id_)"  # KWARG = model field name; VALUE = guarded option identifier


def test_cli_command_guards_shadowed_body_field_end_to_end():
    """The whole write command must parse (a bare `id: str` typer option trips ruff A002; a keyword
    field would be a SyntaxError) and forward the guarded value under the model-field kwarg."""
    model = ir.ObjectModel(name="Widget", fields=(ir.Field(name="id", type=_STRING),))
    op = ir.Operation(
        name="create",
        method="POST",
        path="widgets",
        operation_id="widgets_create",
        body=ir.Body(model="Widget"),
        cli=ir.CliMeta(name="create", documentation="Create a widget."),
    )
    res = ir.Resource(
        domain="tracker",
        resource="widgets",
        security="oauth_token",
        models=(model,),
        operations=(op,),
    )
    block, _imports = resolve._cli_command(res, op, CTX, NAMING, TYPE_MAPPER, DOCSTRINGS)
    ast.parse(block)
    assert "def create(ctx: typer.Context, id_: str) -> None:" in block
    assert "app_ctx.tracker.widgets.create(Widget(id=id_))" in block


def test_assembled_options_requires_write_body():
    """A bodyless op reaching the builder is a wiring bug - fail loud (mirrors `_cli_command`)."""
    op = ir.Operation(name="get", method="GET", path="things", operation_id="things_get")
    res = ir.Resource(
        domain="tracker",
        resource="things",
        security="oauth_token",
        models=(),
        operations=(op,),
    )
    with pytest.raises(ValueError, match="write body"):
        resolve._assembled_options(res, op, TYPE_MAPPER, NAMING)


# --- Task 9 (D5b): `_cli_command` wires the assembled options into a write command ---


def test_cli_command_write_op_assembles_body():
    """A write op's command carries the flat options and forwards the reassembled body."""
    res = _priorities_like_resource()
    op = res.operations[0]
    block, _imports = resolve._cli_command(res, op, CTX, NAMING, TYPE_MAPPER, DOCSTRINGS)
    assert "def create(ctx: typer.Context, key: str, name_ru: str | None = None" in block
    assert "name_en: str | None = None" in block  # one-level ref<LocalizedName> flattened
    assert (
        "Serializer.serialize(app_ctx.tracker.priorities.create("
        "PriorityCreate(key=key, name=LocalizedName(ru=name_ru, en=name_en), "
        "order=order, description=description)), app_ctx.strategy, app_ctx.console)"
    ) in block


def test_cli_page_remaps_model_imports_to_absolute():
    """Finding #5 regression: the relative `.models` `_assembled_options` emits is remapped to the
    resource's ABSOLUTE models module (``.models`` would wrongly resolve inside the cli package)."""
    res = _priorities_like_resource()
    page = resolve.resolve_cli(res, CTX, NAMING, TYPE_MAPPER, DOCSTRINGS)
    assert (
        "from ycli.yandex.tracker.priorities.models import LocalizedName, PriorityCreate"
        in page.import_lines
    )
    assert all(not line.startswith("from .models") for line in page.import_lines)


def test_cli_command_write_op_threads_path_and_query_params():
    """Path params forward positionally (before the reassembled body); query as `name=name`."""
    thing = ir.ObjectModel(name="Thing", fields=(ir.Field(name="label", type=_STRING),))
    edit = ir.Operation(
        name="edit",
        method="POST",
        path="things/{thing_id}",
        operation_id="things_edit",
        params=(
            ir.Param(name="thing_id", loc="path", type=_STRING),
            ir.Param(name="notify", loc="query", type=ir.ScalarType(scalar="boolean")),
        ),
        body=ir.Body(model="Thing"),
        cli=ir.CliMeta(name="edit", documentation="Edit a thing."),
    )
    res = ir.Resource(
        domain="tracker",
        resource="things",
        security="oauth_token",
        models=(thing,),
        operations=(edit,),
    )
    block, _imports = resolve._cli_command(res, edit, CTX, NAMING, TYPE_MAPPER, DOCSTRINGS)
    assert "def edit(ctx: typer.Context, label: str, thing_id: str, notify: bool) -> None:" in block
    assert "app_ctx.tracker.things.edit(thing_id, Thing(label=label), notify=notify)" in block


def test_cli_command_read_op_unchanged():
    """A read op (no body) keeps the byte-identical param-less passthrough and pulls no imports."""
    get_op = ir.Operation(
        name="get",
        method="GET",
        path="me",
        operation_id="me_get",
        cli=ir.CliMeta(
            name="get", documentation="Print the authenticated user (a safe auth probe)."
        ),
    )
    res = ir.Resource(
        domain="tracker",
        resource="me",
        security="oauth_token",
        models=(),
        operations=(get_op,),
    )
    block, imports = resolve._cli_command(res, get_op, CTX, NAMING, TYPE_MAPPER, DOCSTRINGS)
    assert imports == []
    assert block == (
        "@app.command()\n"
        "def get(ctx: typer.Context) -> None:\n"
        '    """Print the authenticated user (a safe auth probe)."""\n'
        "    app_ctx = AppContext.from_typer_context(ctx)\n"
        "    Serializer.serialize(app_ctx.tracker.me.get(), app_ctx.strategy, app_ctx.console)"
    )


# --- Review fix: required-after-defaulted parameter ordering (SyntaxError guard) ---


def test_cli_command_edit_shape_orders_required_path_before_defaulted_options():
    """The real priorities `edit` shape: a REQUIRED path param (`priority_id`) alongside an
    OPTIONAL query and a body whose fields are all optional (so its options carry `= None`).

    Naive source-order concatenation (options, then path, then query) would emit the required
    `priority_id: str` AFTER the defaulted `name_ru: str | None = None` option - a Python
    `SyntaxError` (parameter without a default follows parameter with a default). The generated
    def must instead partition: every no-default decl first, then every defaulted decl.
    """
    priority_edit = ir.ObjectModel(
        name="PriorityEdit", fields=(ir.Field(name="name_ru", type=_STRING, optional=True),)
    )
    edit = ir.Operation(
        name="edit",
        method="POST",
        path="priorities/{priority_id}",
        operation_id="priorities_edit",
        params=(
            ir.Param(name="priority_id", loc="path", type=_STRING),
            ir.Param(
                name="version", loc="query", type=ir.ScalarType(scalar="integer"), optional=True
            ),
        ),
        body=ir.Body(model="PriorityEdit"),
        cli=ir.CliMeta(name="edit", documentation="Edit a priority."),
    )
    res = ir.Resource(
        domain="tracker",
        resource="priorities",
        security="oauth_token",
        models=(priority_edit,),
        operations=(edit,),
    )
    block, _imports = resolve._cli_command(res, edit, CTX, NAMING, TYPE_MAPPER, DOCSTRINGS)
    ast.parse(block)  # no SyntaxError - the crux of the regression
    def_line = next(line for line in block.splitlines() if line.startswith("def edit("))
    assert def_line.index("priority_id: str") < def_line.index("= None")


def test_assembled_options_orders_required_scalar_before_defaulted_scalar():
    """A body `{note?: str, key: str}` - an optional field declared BEFORE a required one -
    must still emit the required `key: str` before the defaulted `note: str | None = None` in
    the command signature (the partition reorders across the body options too, not just
    across options/path/query)."""
    model = ir.ObjectModel(
        name="NotePatch",
        fields=(
            ir.Field(name="note", type=_STRING, optional=True),
            ir.Field(name="key", type=_STRING),
        ),
    )
    op = ir.Operation(
        name="write",
        method="POST",
        path="things",
        operation_id="things_write",
        body=ir.Body(model="NotePatch"),
        cli=ir.CliMeta(name="write", documentation="Write a thing."),
    )
    res = ir.Resource(
        domain="tracker",
        resource="things",
        security="oauth_token",
        models=(model,),
        operations=(op,),
    )
    block, _imports = resolve._cli_command(res, op, CTX, NAMING, TYPE_MAPPER, DOCSTRINGS)
    ast.parse(block)  # no SyntaxError
    def_line = next(line for line in block.splitlines() if line.startswith("def write("))
    assert def_line.index("key: str") < def_line.index("note: str | None = None")
