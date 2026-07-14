"""Direct unit tests for the loader's neutral-type lowering.

The ``me`` walking-skeleton spec makes every field ``optional: true``, so the loader's
*non-optional* path — its primary job — and the no-explicit-default / explicit-default arms of
``_field`` are never exercised by the end-to-end golden tests. These tests call the loader's real
``_lower_type`` / ``_field`` / ``_require_found`` and ``ir.Resource.model`` directly (no lowering
is reimplemented here) so the core logic is asserted, not just incidentally line-covered.
"""

import pytest

from refract import ir
from refract.loader import FieldSpec, _field, _lower_type, _require_found

# neutral scalar name -> lowered NON-optional Python type-string (the loader's _SCALAR_TYPES map).
_SCALARS = [
    ("string", "str"),
    ("integer", "int"),
    ("number", "float"),
    ("boolean", "bool"),
    ("any", "Any"),
]


@pytest.mark.parametrize(("neutral", "python_type"), _SCALARS)
def test_lower_type_non_optional_is_bare_type_with_no_default(neutral, python_type):
    # The loader's MAIN job: a required scalar lowers to the bare type, NO ` | None`, NO default.
    assert _lower_type(neutral, optional=False) == (python_type, None)


@pytest.mark.parametrize(("neutral", "python_type"), _SCALARS)
def test_lower_type_optional_unions_none_and_implies_none_default(neutral, python_type):
    # optional -> ``<type> | None`` with the implied literal-``"None"`` default text.
    assert _lower_type(neutral, optional=True) == (f"{python_type} | None", "None")


def test_field_optional_without_explicit_default_gets_implied_none():
    field = _field(FieldSpec(name="uid", type="integer", optional=True))
    assert field.type == "int | None"
    assert field.optional is True
    assert field.default == "None"


def test_field_non_optional_renders_no_default():
    field = _field(FieldSpec(name="uid", type="integer"))
    assert field.type == "int"
    assert field.optional is False
    assert field.default is None


def test_field_explicit_optional_default_is_passed_through():
    # _field's explicit-default arm: the spec's own default wins over the implied ``"None"``.
    field = _field(FieldSpec(name="count", type="integer", optional=True, default="0"))
    assert field.type == "int | None"
    assert field.default == "0"


def test_field_explicit_non_optional_default_is_passed_through():
    # Same arm on a required field: the implied default is None, so the spec default must win.
    field = _field(FieldSpec(name="page", type="integer", default="1"))
    assert field.optional is False
    assert field.default == "1"


def test_require_found_none_returns_none():
    # The no-guard arm — never taken by ``me`` (whose read tool always declares a guard).
    assert _require_found(None) is None


def test_resource_model_finds_the_second_of_multiple_models():
    # Exercises the lookup loop past its first candidate (``me`` carries only one model).
    first = ir.Model(name="First")
    second = ir.Model(name="Second")
    res = ir.Resource(
        domain="tracker",
        resource="things",
        base_url="https://api.example.net/v3",
        security="oauth_token",
        models=(first, second),
        operations=(),
    )
    assert res.model("Second") is second
