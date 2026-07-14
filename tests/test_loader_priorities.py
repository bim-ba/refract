"""Loader tests for the body-carrying ``tracker/priorities`` resource (A.2 Task 1).

Exercises the IR/loader extensions ``me`` never touched: a write ``body`` registry entry
(``TypedModel``), path/query ``params``, and ``ref<Model>`` type lowering — asserted against the
real loaded IR, not reimplemented here. ``me``'s own loader tests (``test_loader.py``,
``test_loader_lowering.py``) stay the regression anchor for the read-only, body-less, param-less
shape.
"""

from refract import ir


def test_loads_priorities_resource(priorities_resource):
    res = priorities_resource
    assert isinstance(res, ir.Resource)
    assert res.domain == "tracker" and res.resource == "priorities"
    assert res.documentation == "Tracker /priorities resource package."


def test_five_models_with_correct_kinds(priorities_resource):
    models = {model.name: model for model in priorities_resource.models}
    assert set(models) == {
        "Priority",
        "PriorityList",
        "LocalizedName",
        "PriorityCreate",
        "PriorityUpdate",
    }
    assert models["Priority"].kind == "object"
    assert models["LocalizedName"].kind == "object"
    assert models["PriorityCreate"].kind == "object"
    assert models["PriorityUpdate"].kind == "object"
    assert models["PriorityList"].kind == "root_list"
    assert models["PriorityList"].item == "Priority"


def test_priority_create_key_is_required_with_no_rendered_default_and_a_description(
    priorities_resource,
):
    key = next(f for f in priorities_resource.model("PriorityCreate").fields if f.name == "key")
    assert key.optional is False
    assert key.default is None
    assert key.type == "str"
    assert key.description == "Key of the new priority."


def test_priority_create_name_field_lowers_ref_type_to_the_bare_model_name(priorities_resource):
    name = next(f for f in priorities_resource.model("PriorityCreate").fields if f.name == "name")
    assert name.type == "LocalizedName"
    assert name.optional is False
    assert name.description == "Localized display name of the priority."


def test_priority_update_name_field_is_an_optional_model_ref(priorities_resource):
    name = next(f for f in priorities_resource.model("PriorityUpdate").fields if f.name == "name")
    assert name.type == "LocalizedName | None"
    assert name.optional is True
    assert name.default == "None"


def test_create_operation_carries_a_typed_model_body(priorities_resource):
    op = next(op for op in priorities_resource.operations if op.name == "create")
    assert op.body is not None
    assert op.body.mode == "TypedModel"
    assert op.body.model == "PriorityCreate"
    assert op.body.dump == "by_alias=True, exclude_none=True"
    assert op.mcp is not None
    assert op.mcp.safety == "WRITE"


def test_edit_operation_carries_a_typed_model_body_and_a_version_query_param(priorities_resource):
    op = next(op for op in priorities_resource.operations if op.name == "edit")
    assert op.body is not None
    assert op.body.mode == "TypedModel"
    assert op.body.model == "PriorityUpdate"
    assert op.body.dump == "by_alias=True, exclude_none=True"
    version = next(param for param in op.params if param.name == "version")
    assert isinstance(version, ir.Param)
    assert version.loc == "query"
    assert version.type == "int | None"
    assert version.alias == "version"
    assert version.default == "None"
    assert op.mcp is not None
    assert op.mcp.safety == "WRITE_IDEMPOTENT"


def test_list_operation_is_bodyless_and_paramless_with_ro_safety(priorities_resource):
    op = next(op for op in priorities_resource.operations if op.name == "list")
    assert op.body is None
    assert op.params == ()
    assert op.response_model == "PriorityList"
    assert op.mcp is not None
    assert op.mcp.safety == "RO"
