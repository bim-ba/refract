import pytest
from pydantic import TypeAdapter, ValidationError

from refract.ir.types import ListType, MapType, NeutralType, RefType, ScalarType

_adapter = TypeAdapter(NeutralType)


def test_scalar_parses_by_discriminator():
    assert _adapter.validate_python({"kind": "scalar", "scalar": "integer"}) == ScalarType(
        scalar="integer"
    )


def test_ref_parses():
    assert _adapter.validate_python({"kind": "ref", "target": "Me"}) == RefType(target="Me")


def test_recursive_list_of_ref():
    parsed = _adapter.validate_python(
        {"kind": "list", "item": {"kind": "ref", "target": "Priority"}}
    )
    assert parsed == ListType(item=RefType(target="Priority"))


def test_map_is_recursive_both_sides():
    parsed = _adapter.validate_python(
        {
            "kind": "map",
            "key": {"kind": "scalar", "scalar": "string"},
            "value": {"kind": "scalar", "scalar": "integer"},
        }
    )
    assert parsed == MapType(key=ScalarType(scalar="string"), value=ScalarType(scalar="integer"))


def test_variants_are_frozen_and_hashable():
    s = ScalarType(scalar="string")
    with pytest.raises(ValidationError):
        s.scalar = "integer"  # ty: ignore[invalid-assignment]  # frozen
    assert hash(s) == hash(ScalarType(scalar="string"))
    assert {s, ScalarType(scalar="string")} == {s}  # dedups -> hashable


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        _adapter.validate_python({"kind": "bogus"})
