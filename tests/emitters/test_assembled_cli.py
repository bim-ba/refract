"""Task 8 (D5a): the Assembled-CLI option builder - `_assembled_options` walks a write op's body
model into flat typer options + a reassembly expression, with the Q1 escape hatch (`SpecError`
suggesting a `handler:`) for any shape past scalar + one-level ref.

Fixtures are synthetic (built in-Python, mirroring examples/ycli-tracker/.../priorities) so the
walk is exercised without loading a spec file.
"""

from __future__ import annotations

import pytest

from refract import ir
from refract.emitters.python import resolve
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.types import PythonTypeMapper
from refract.spec import SpecError

NAMING = PythonNaming()
TYPE_MAPPER = PythonTypeMapper()

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
