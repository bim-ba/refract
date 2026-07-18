from refract.emitters.api import Import
from refract.emitters.python.types import PythonTypeMapper
from refract.ir.types import ListType, LiteralType, MapType, RefType, ScalarType, UnionType

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


def test_undiscriminated_scalar_union_renders_pep604():
    union = UnionType(
        variants=(ScalarType(scalar="string"), ScalarType(scalar="integer")), discriminator=None
    )
    assert m.render(union, optional=False).text == "str | int"


def test_undiscriminated_union_optional_wraps_whole():
    union = UnionType(
        variants=(ScalarType(scalar="string"), ScalarType(scalar="integer")), discriminator=None
    )
    assert m.render(union, optional=True).text == "str | int | None"


def test_undiscriminated_union_of_refs_renders_bare_names():
    union = UnionType(
        variants=(RefType(target="Paragraph"), RefType(target="Heading1Block")), discriminator=None
    )
    assert m.render(union, optional=False).text == "Paragraph | Heading1Block"


def test_union_with_any_variant_pulls_the_typing_import():
    union = UnionType(
        variants=(ScalarType(scalar="any"), ScalarType(scalar="integer")), discriminator=None
    )
    rendered = m.render(union, optional=False)
    assert any(imp.module == "typing" and imp.name == "Any" for imp in rendered.imports)


def test_discriminated_union_base_is_bare_and_carries_discriminator():
    union = UnionType(
        variants=(RefType(target="Paragraph"), RefType(target="Heading1Block")),
        discriminator="type",
    )
    rendered = m.render(union, optional=False)
    assert rendered.text == "Paragraph | Heading1Block"  # NO Annotated wrapper baked in
    assert rendered.discriminator == "type"


def test_literal_type_lowers_to_typing_literal():
    rendered = m.render(LiteralType(value="heading_1"), optional=False)
    assert rendered.text == 'Literal["heading_1"]'
    assert ("typing", "Literal") in {(i.module, i.name) for i in rendered.imports}


def test_int64_format_keeps_int_and_names_a_coercer():
    from refract.ir.types import ScalarType

    rendered = m.render(ScalarType(scalar="integer", format="int64"), optional=False)
    assert rendered.text == "int"
    assert rendered.coercer == "coerce_int64"


def test_rfc2822_format_swaps_to_datetime():
    from refract.ir.types import ScalarType

    rendered = m.render(ScalarType(scalar="string", format="rfc2822"), optional=False)
    assert rendered.text == "datetime"
    assert ("datetime", "datetime") in {(i.module, i.name) for i in rendered.imports}


def test_unknown_format_is_a_noop():
    from refract.ir.types import ScalarType

    rendered = m.render(ScalarType(scalar="integer", format="weird"), optional=False)
    assert rendered.text == "int" and rendered.coercer is None


def test_int64_format_optional_wraps_coercer_base_with_pep604_none():
    """The `| None` wrap in `render` is OUTSIDE the coerced base text, and `coercer` still
    survives the optional rebuild (mirrors the `discriminator` threading test)."""
    rendered = m.render(ScalarType(scalar="integer", format="int64"), optional=True)
    assert rendered.text == "int | None"
    assert rendered.coercer == "coerce_int64"
