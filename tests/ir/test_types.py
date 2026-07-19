import pytest
from pydantic import TypeAdapter, ValidationError

from refract.ir.types import (
    ListType,
    LiteralType,
    MapType,
    NeutralType,
    RefType,
    ScalarType,
    UnionType,
)

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


def test_union_type_round_trips_like_the_other_kinds():
    union = UnionType(
        variants=(ScalarType(scalar="string"), RefType(target="X")), discriminator=None
    )
    assert union.kind == "union"
    dumped = union.model_dump()
    assert UnionType.model_validate(dumped) == union


def test_union_type_discriminated_carries_the_tag_field_name():
    union = UnionType(
        variants=(RefType(target="Paragraph"), RefType(target="Heading1Block")),
        discriminator="type",
    )
    assert union.discriminator == "type"


def test_union_type_nests_inside_list_and_stays_hashable():
    inner = UnionType(variants=(ScalarType(scalar="string"), ScalarType(scalar="integer")))
    listed = ListType(item=inner)
    assert listed.item == inner
    assert hash(listed)  # frozen -> hashable


def test_union_type_requires_at_least_two_variants():
    with pytest.raises(ValidationError):
        UnionType(variants=(ScalarType(scalar="string"),))


def test_discriminated_union_variants_must_all_be_refs():
    """A1: a DISCRIMINATED union whose variants are not all `ref<Model>` is an illegal state that
    pydantic cannot honor (a discriminated union needs BaseModel arms). The IR TYPE rejects it at
    construction - not only the spec loader - so a second IR producer (an OpenAPI importer) cannot
    build the illegal combo and detonate at generated-code import time far from the cause."""
    with pytest.raises(ValidationError):
        UnionType(variants=(ScalarType(scalar="string"), RefType(target="X")), discriminator="kind")


def test_undiscriminated_union_may_mix_non_ref_variants():
    """The invariant is scoped to DISCRIMINATED unions: an undiscriminated union still mixes any
    type-exprs (a scalar + a ref), so this must NOT raise."""
    union = UnionType(variants=(ScalarType(scalar="string"), RefType(target="X")))
    assert union.discriminator is None


def test_literal_type_round_trips():
    lit = LiteralType(value="heading_1")
    assert LiteralType.model_validate(lit.model_dump()) == lit


def test_scalar_type_format_defaults_none_and_round_trips():
    st = ScalarType(scalar="integer", format="int64")
    assert st.format == "int64"
    assert ScalarType(scalar="integer").format is None
    assert ScalarType.model_validate(st.model_dump()) == st
