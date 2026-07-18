import pytest
from pydantic import TypeAdapter, ValidationError

from refract import ir
from refract.ir.types import RefType, ScalarType


def _field(name="uid", type=ScalarType(scalar="integer"), **kw):
    return ir.Field(name=name, type=type, **kw)


def test_field_carries_neutral_type_not_python_string():
    f = _field(optional=True)
    assert f.type == ScalarType(scalar="integer")  # NOT "int | None"


def test_object_and_root_list_are_distinct_variants():
    me = ir.ObjectModel(name="Me", fields=(_field(),))
    priorities = ir.RootListModel(name="PriorityList", item="Priority")
    assert me.kind == "object"
    assert priorities.kind == "root_list"
    assert me.fields[0].name == "uid"
    assert priorities.item == "Priority"


def test_model_union_parses_by_discriminator():
    adapter = TypeAdapter(ir.Model)
    obj = adapter.validate_python(
        {
            "kind": "object",
            "name": "Me",
            "fields": [{"name": "uid", "type": {"kind": "scalar", "scalar": "integer"}}],
        }
    )
    lst = adapter.validate_python({"kind": "root_list", "name": "PriorityList", "item": "Priority"})
    assert isinstance(obj, ir.ObjectModel)
    assert isinstance(lst, ir.RootListModel)


def test_resource_is_frozen_and_hashable():
    res = ir.Resource(
        domain="tracker",
        resource="me",
        security="oauth_token",
        models=(ir.ObjectModel(name="Me", fields=(_field(),)),),
        operations=(ir.Operation(name="get", method="GET", path="myself", operation_id="me_get"),),
    )
    assert hash(res)  # tuple collections keep it hashable
    with pytest.raises(ValidationError):
        res.domain = "x"  # ty: ignore[invalid-assignment]  # frozen


def test_list_input_is_coerced_to_tuple():
    m = ir.ObjectModel(name="Me", fields=[_field()])  # list input
    assert isinstance(m.fields, tuple)


def test_ref_field_type_roundtrips():
    f = _field(type=RefType(target="LocalizedName"))
    assert f.type == RefType(target="LocalizedName")


def test_resource_model_accessor_and_domain_title():
    me = ir.ObjectModel(name="Me", fields=(_field(),))
    plist = ir.RootListModel(name="PriorityList", item="Priority")
    res = ir.Resource(
        domain="tracker", resource="me", security="oauth_token", models=(me, plist), operations=()
    )
    assert res.model("Me") is me
    assert res.model("PriorityList") is plist
    resolved = res.model("Me")
    assert isinstance(resolved, ir.ObjectModel)  # Me is the ObjectModel branch
    assert resolved.fields[0].name == "uid"
    assert res.domain_title == "Tracker"
    with pytest.raises(KeyError):
        res.model("Nope")


def test_safety_and_test_kind_accept_string_values():
    assert ir.Safety("RO") is ir.Safety.RO
    assert ir.Safety("DESTRUCTIVE") is ir.Safety.DESTRUCTIVE
    assert ir.TestKind("client") is ir.TestKind.CLIENT
    assert ir.TestKind("mcp_guard") is ir.TestKind.MCP_GUARD


def test_body_carries_dump_flags_and_is_frozen():
    b = ir.Body(model="PriorityCreate", by_alias=False, omit_none=False)
    assert b.mode == "typed_model"
    assert (b.by_alias, b.omit_none) == (False, False)
    with pytest.raises(ValidationError):
        b.by_alias = True  # ty: ignore[invalid-assignment]  # frozen
