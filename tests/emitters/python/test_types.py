import pytest

from refract.emitters.api import Import
from refract.emitters.python.types import PythonTypeMapper
from refract.ir.types import ListType, MapType, RefType, ScalarType, UnionType

m = PythonTypeMapper()


def test_scalar_lowering():
    assert m.render(ScalarType(scalar="integer"), optional=False).text == "int"
    assert m.render(ScalarType(scalar="string"), optional=False).text == "str"
    assert m.render(ScalarType(scalar="number"), optional=False).text == "float"
    assert m.render(ScalarType(scalar="boolean"), optional=False).text == "bool"


def test_optional_appends_none_and_default():
    rt = m.render(ScalarType(scalar="integer"), optional=True)
    assert rt.text == "int | None"
    assert m.null_default(ScalarType(scalar="integer"), optional=True) == "None"
    assert m.null_default(ScalarType(scalar="integer"), optional=False) is None


def test_ref_is_bare_model_name():
    assert m.render(RefType(target="LocalizedName"), optional=False).text == "LocalizedName"


def test_any_pulls_typing_import():
    rt = m.render(ScalarType(scalar="any"), optional=False)
    assert rt.text == "Any" and Import("typing", "Any") in rt.imports


def test_containers():
    assert m.render(ListType(item=ScalarType(scalar="string")), optional=False).text == "list[str]"
    assert (
        m.render(
            MapType(key=ScalarType(scalar="string"), value=ScalarType(scalar="integer")),
            optional=False,
        ).text
        == "dict[str, int]"
    )


def test_union_is_temporarily_not_implemented():
    """TEMPORARY (Task 2 placeholder): Task 3 replaces this arm with real lowering + this test."""
    union = UnionType(variants=(ScalarType(scalar="string"), ScalarType(scalar="integer")))
    with pytest.raises(NotImplementedError):
        m.render(union, optional=False)
