import pytest

from refract.ir.types import ListType, MapType, RefType, ScalarType
from refract.spec.loader import SpecError, parse_neutral_type


@pytest.mark.parametrize(
    "text,expected",
    [
        ("string", ScalarType(scalar="string")),
        ("integer", ScalarType(scalar="integer")),
        (" boolean ", ScalarType(scalar="boolean")),
        ("ref<LocalizedName>", RefType(target="LocalizedName")),
        ("list<string>", ListType(item=ScalarType(scalar="string"))),
        (
            "map<string,integer>",
            MapType(key=ScalarType(scalar="string"), value=ScalarType(scalar="integer")),
        ),
        ("list<ref<Priority>>", ListType(item=RefType(target="Priority"))),
        (
            "map<string,list<integer>>",
            MapType(
                key=ScalarType(scalar="string"), value=ListType(item=ScalarType(scalar="integer"))
            ),
        ),
        (
            # nested generic as the KEY (not the value): the top-level comma sits AFTER a nested
            # "<...>" span, exercising the bracket-depth-aware split in `_split_top_comma`.
            "map<list<string>,integer>",
            MapType(
                key=ListType(item=ScalarType(scalar="string")), value=ScalarType(scalar="integer")
            ),
        ),
    ],
)
def test_parses(text, expected):
    assert parse_neutral_type(text) == expected


@pytest.mark.parametrize("bad", ["", "int", "ref<>", "list<>", "map<string>", "bogus<x>"])
def test_rejects_malformed(bad):
    with pytest.raises(SpecError):
        parse_neutral_type(bad)
