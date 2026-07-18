import ast

import pytest

from refract import ir
from refract.emitters.api import EmitContext, Import
from refract.emitters.python import resolve
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.types import PythonTypeMapper
from refract.ir.types import UnionType
from refract.spec import SpecError

NAMING = PythonNaming()
TYPE_MAPPER = PythonTypeMapper()
DOCSTRINGS = PythonDocstrings()
CTX = EmitContext(package_root="ycli.yandex.tracker")


def test_render_imports_groups_and_merges():
    out = resolve.render_imports(
        (Import(".models", "Me"), Import(".models", "Priority"), Import("typing", "Any"))
    )
    assert "from .models import Me, Priority" in out
    assert "from typing import Any" in out


def test_signature_params_inserts_star_for_keyword_only():
    assert resolve.signature_params(
        ("self", "priority_id: str"), ("version: int | None = None",)
    ) == ("self", "priority_id: str", "*", "version: int | None = None")


def test_signature_params_no_star_when_no_keyword_only():
    assert resolve.signature_params(("self",), ()) == ("self",)


def test_indent_lines_skips_blanks():
    assert resolve.indent_lines(("a", "", "b"), "    ") == ("    a", "", "    b")


def test_py_str_escapes_embedded_quotes():
    """The hardening this helper exists for: an unescaped `"` would emit invalid Python."""
    literal = resolve.py_str('The "primary" key')
    assert literal == '"The \\"primary\\" key"'
    assert ast.literal_eval(literal) == 'The "primary" key'


@pytest.mark.parametrize(
    "value",
    [
        'The "primary" key',
        "back\\slash",
        "line\nbreak",
        'mixed "quotes" and \\ backslash and \n newline',
        "em—dash and café",  # non-ASCII stays literal
        "",
    ],
)
def test_py_str_round_trips_and_is_valid_python(value):
    literal = resolve.py_str(value)
    # (a) round-trips back to the original value
    assert ast.literal_eval(literal) == value
    # (b) is valid Python when used in an assignment
    tree = ast.parse(f"x = {literal}")
    assert isinstance(tree.body[0], ast.Assign)


def test_model_field_with_quoted_description_emits_parseable_source():
    """A `description` containing a `"` must not corrupt the emitted `Field(...)` call."""
    field = ir.Field(
        name="key",
        type=ir.ScalarType(scalar="string"),
        description='The "primary" key of the priority.',
    )
    decl, _imports = resolve._model_field(field, TYPE_MAPPER)
    ast.parse(f"class M:\n{decl}\n")  # must not raise SyntaxError
    assert 'description="The \\"primary\\" key of the priority."' in decl


def test_model_field_required_no_description_omits_none_default():
    """A required (non-optional) field with no description/alias renders `name: type` with NO
    `= None`. `= None` would wrongly default a required field to None and mistype a non-None
    annotation (e.g. `str = None`). Surfaced by the synthesized `Literal[tag]` discriminator field,
    which is required and description-less."""
    field = ir.Field(name="key", type=ir.ScalarType(scalar="string"))  # required, no desc/alias
    decl, _imports = resolve._model_field(field, TYPE_MAPPER)
    assert decl == "    key: str"  # NOT "    key: str = None"


def test_model_field_with_alias_emits_field_alias():
    """`field.alias` must render `Field(alias=...)` even without a description."""
    field = ir.Field(name="type_", type=ir.ScalarType(scalar="string"), alias="type")
    decl, _imports = resolve._model_field(field, TYPE_MAPPER)
    ast.parse(f"class M:\n{decl}\n")  # must not raise SyntaxError
    assert 'alias="type"' in decl
    assert "Field(" in decl


def test_int64_field_wraps_annotated_before_validator():
    """A formatted scalar field wraps `Annotated[<base>, BeforeValidator(<coercer>)]` - independent
    of the discriminator branch (format is scalar-only; a union is never a scalar, so the two
    never co-occur on one field). A REQUIRED coerced field follows the same convention as any other
    required field: NO `= None` (coercion does not change whether a field is required)."""
    line, imports = resolve._model_field(
        ir.Field(name="cores", type=ir.ScalarType(scalar="integer", format="int64")), TYPE_MAPPER
    )
    assert (
        line == "    cores: Annotated[int, BeforeValidator(coerce_int64)]"
    )  # required -> no = None
    assert {("pydantic", "BeforeValidator"), ("typing", "Annotated")} <= {
        (i.module, i.name) for i in imports
    }


def test_int64_optional_field_puts_none_outside_the_coercer_annotated():
    """`render`'s optional wrap applies `| None` OUTSIDE the coerced base (`Annotated[int,
    BeforeValidator(...)] | None`), not inside it - `_model_field` wraps whatever `rendered.text`
    already is, it never re-derives the optional suffix itself."""
    line, _imports = resolve._model_field(
        ir.Field(name="cores", type=ir.ScalarType(scalar="integer", format="int64"), optional=True),
        TYPE_MAPPER,
    )
    assert line == "    cores: Annotated[int, BeforeValidator(coerce_int64)] | None = None"


def test_resolve_models_imports_coercer_from_shared_base_module():
    """A coerced field pulls its coercer helper (hand-written in the shared base module, mirroring
    the existing hand-written `APIModel` convention) alongside the `Annotated`/`BeforeValidator`
    wiring - refract emits only the wiring, never the coercion logic itself."""
    model = ir.ObjectModel(
        name="Widget",
        fields=(ir.Field(name="cores", type=ir.ScalarType(scalar="integer", format="int64")),),
    )
    res = ir.Resource(
        domain="tracker", resource="widgets", security="oauth_token", models=(model,), operations=()
    )
    page = resolve.resolve_models(res, CTX, NAMING, TYPE_MAPPER, DOCSTRINGS)
    assert "from ycli.yandex.models import APIModel, coerce_int64" in page.import_lines


_UNION = UnionType(
    variants=(ir.RefType(target="Paragraph"), ir.RefType(target="Heading1Block")),
    discriminator="type",
)


def test_discriminated_field_emits_single_annotated_field_call():
    """A discriminated union field renders ONE `Annotated[A | B, Field(discriminator=...)]` -
    never a bare union nor a `= Field(...)` default (pydantic requires the discriminator inside
    `Annotated[...]`)."""
    line, imports = resolve._model_field(ir.Field(name="block", type=_UNION), TYPE_MAPPER)
    assert line == '    block: Annotated[Paragraph | Heading1Block, Field(discriminator="type")]'
    assert {("typing", "Annotated"), ("pydantic", "Field")} <= {(i.module, i.name) for i in imports}


def test_discriminated_field_with_description_merges_one_field_call():
    """A discriminated field with a description merges INTO the same `Field(...)` call - never
    two nested `Field(...)` calls on one annotation."""
    line, _imports = resolve._model_field(
        ir.Field(name="block", type=_UNION, description="A block."), TYPE_MAPPER
    )
    assert line == (
        "    block: Annotated[Paragraph | Heading1Block, "
        'Field(discriminator="type", description="A block.")]'
    )
    assert line.count("Field(") == 1  # not two nested Field(...) calls


_STRING = ir.ScalarType(scalar="string")


def _shadowed_op() -> ir.Operation:
    """A GET with a builtin-named path param (`id`) and a builtin-named query param (`type`)."""
    return ir.Operation(
        name="fetch",
        method="GET",
        path="widget/{id}",
        operation_id="widget_fetch",
        params=(
            ir.Param(name="id", loc="path", type=_STRING),
            ir.Param(name="type", loc="query", type=_STRING, optional=True),
        ),
        response_model="Widget",
    )


def test_request_function_guards_shadowed_path_and_query_identifiers():
    """A path param `id` / query param `type` shadow builtins: the emitted Python IDENTIFIERS are
    suffixed (`id_`, `type_`), the path f-string references the guarded var, and the query dict
    KEY stays the wire name (`type`) while its VALUE is the guarded identifier."""
    text, _imports = resolve._request_function(_shadowed_op(), NAMING, TYPE_MAPPER, DOCSTRINGS)
    ast.parse(text)  # a bare `def fetch(id: str, ...)` would need no parse-guard, but `class` would
    assert "def fetch(id_: str, *, type_: str | None = None)" in text  # guarded identifiers
    assert 'path=f"widget/{id_}"' in text  # path references the guarded var; the URL is unchanged
    assert 'query={"type": type_}' in text  # wire KEY stays `type`; VALUE is the guarded identifier


def test_request_function_guards_keyword_path_param():
    """A keyword path param (`class`) is an outright SyntaxError unless guarded to `class_`."""
    op = ir.Operation(
        name="fetch",
        method="GET",
        path="node/{class}",
        operation_id="node_fetch",
        params=(ir.Param(name="class", loc="path", type=_STRING),),
        response_model="Node",
    )
    text, _imports = resolve._request_function(op, NAMING, TYPE_MAPPER, DOCSTRINGS)
    ast.parse(text)  # `def fetch(class: str)` would raise SyntaxError here
    assert "def fetch(class_: str)" in text
    assert 'path=f"node/{class_}"' in text


def test_client_method_guards_shadowed_identifiers():
    """The client sugar method mirrors the guard: guarded signature + guarded builder call."""
    text, _imports = resolve._client_method(_shadowed_op(), NAMING, TYPE_MAPPER, DOCSTRINGS)
    ast.parse(f"class C:\n{text}")  # method text is indented one level to sit inside the class
    assert "def fetch(self, id_: str, *, type_: str | None = None)" in text
    assert "_requests.fetch(id_, type_=type_)" in text  # positional path + keyword query, guarded


def test_mcp_tool_guards_shadowed_identifiers():
    """The guard flows through `signature_and_call` into the MCP tool signature + client call."""
    op = _shadowed_op().model_copy(
        update={
            "mcp": ir.McpMeta(
                name="widget_fetch",
                safety=ir.Safety.RO,
                title="Fetch a widget",
                documentation="Fetch a widget.",
            )
        }
    )
    res = ir.Resource(
        domain="tracker", resource="widgets", security="oauth_token", models=(), operations=(op,)
    )
    text, _imports = resolve._mcp_tool(res, op, NAMING, TYPE_MAPPER, DOCSTRINGS)
    ast.parse(text)
    assert "id_: str" in text
    assert "type_: str | None = None" in text
    assert "client.widgets.fetch(id_, type_=type_)" in text


def test_cli_command_raises_without_cli_facet(me_resource):
    op = me_resource.operations[0].model_copy(update={"cli": None})
    with pytest.raises(ValueError, match="no cli facet"):
        resolve._cli_command(me_resource, op, CTX, NAMING, TYPE_MAPPER, DOCSTRINGS)


def test_mcp_tool_raises_without_mcp_facet(me_resource):
    op = me_resource.operations[0].model_copy(update={"mcp": None})
    with pytest.raises(ValueError, match="no mcp facet"):
        resolve._mcp_tool(me_resource, op, NAMING, TYPE_MAPPER, DOCSTRINGS)


def test_resolve_mcp_skips_operations_without_mcp_facet(me_resource):
    bare = me_resource.operations[0].model_copy(update={"name": "bare", "mcp": None})
    res = me_resource.model_copy(update={"operations": (*me_resource.operations, bare)})
    ctx = EmitContext(package_root="ycli.yandex.tracker")
    page = resolve.resolve_mcp(res, ctx, NAMING, TYPE_MAPPER, DOCSTRINGS)
    # one real mcp-faceted op -> one tool; the bare (mcp=None) op contributes nothing
    assert len(page.tools) == 1


def test_resolve_mcp_omits_response_model_import_when_none():
    """A bodyless, responseless mcp-faceted op (e.g. a delete) must skip the response-model
    import: the tool signature returns ``-> None`` and no ``models_module`` import is emitted."""
    op = ir.Operation(
        name="delete",
        method="DELETE",
        path="widget/{id}",
        operation_id="widget_delete",
        params=(ir.Param(name="id", loc="path", type=_STRING),),
        mcp=ir.McpMeta(
            name="widget_delete",
            safety=ir.Safety.DESTRUCTIVE,
            title="Delete a widget",
            documentation="Delete a widget.",
        ),
    )
    res = ir.Resource(
        domain="tracker", resource="widgets", security="oauth_token", models=(), operations=(op,)
    )
    ctx = EmitContext(package_root="ycli.yandex.tracker")
    page = resolve.resolve_mcp(res, ctx, NAMING, TYPE_MAPPER, DOCSTRINGS)
    assert "-> None:" in page.tools[0]
    assert not any("widgets.models" in line for line in page.import_lines)


def test_body_test_imports_skips_nested_ref_scan_for_non_object_model():
    """A body model that resolves to something other than ``ObjectModel`` (e.g. a bare
    ``RootListModel``) has no ``.fields`` to scan for nested refs - the import list is just the
    body model itself."""
    tags = ir.RootListModel(name="Tags", item="str")
    res = ir.Resource(
        domain="tracker", resource="things", security="oauth_token", models=(tags,), operations=()
    )
    models_module = "ycli.yandex.tracker.things.models"
    imports = resolve._body_test_imports(res, ir.Body(model="Tags"), models_module)
    assert imports == (Import(models_module, "Tags"),)


def test_resolve_tests_cli_only_op_drops_client_surface():
    """An op whose only test case is CLI-kind (no CLIENT case): the module doc drops the
    "client" surface label and the import block skips the client-class + response-model imports.
    The ``_PAYLOAD_`` constant IS still emitted: ``_stub`` references ``_PAYLOAD_<op>`` for every
    non-guard case (client/cli/mcp alike), so a cli-only op that omitted it would reference an
    undefined name (C1). The payload is read from the sole non-guard case's fixture."""
    case = ir.TestCase(
        name="widgets_list_cli",
        kind=ir.TestKind.CLI,
        http_method="GET",
        path="widgets",
        status=200,
        response_json=[],
        has_json=True,
        asserts=["res.exit_code == 0"],
        call="",
    )
    op = ir.Operation(
        name="list",
        method="GET",
        path="widgets",
        operation_id="widgets_list",
        response_model="WidgetList",
        cli=ir.CliMeta(name="list", documentation="List widgets."),
        tests=(case,),
    )
    res = ir.Resource(
        domain="tracker", resource="widgets", security="oauth_token", models=(), operations=(op,)
    )
    ctx = EmitContext(
        package_root="ycli.yandex.tracker",
        config=ir.ClientConfig(
            name="tracker", server=ir.Server(base_url="https://api.example"), auth=()
        ),
    )
    page = resolve.resolve_tests(res, ctx, NAMING, TYPE_MAPPER, DOCSTRINGS)
    assert page.doc_block == ('"""Tracker /widgets resource - CLI, HTTP stubbed."""',)
    assert page.import_lines == (
        "import json",
        "import responses",
        "from typer.testing import CliRunner",
        "import ycli.cli.app as cli",
    )
    assert page.constants == (
        '_URL_list = "https://api.example/widgets"',
        "_PAYLOAD_list = []",
        "_runner = CliRunner()",
    )


def test_resolve_tests_guard_only_op_emits_no_payload():
    """An op whose only test case is an MCP guard: the guard stub inlines its own ``{}`` fixture
    (never reads ``_PAYLOAD_``), so no payload constant is emitted. Closes the fallback branch of
    the payload-case selection (no client case AND no other non-guard case)."""
    case = ir.TestCase(
        name="widgets_delete_guard",
        kind=ir.TestKind.MCP_GUARD,
        http_method="DELETE",
        path="widgets/x",
        status=404,
        response_json={"error": "not_found"},
        has_json=True,
        asserts=(),
        call="",
    )
    op = ir.Operation(
        name="delete",
        method="DELETE",
        path="widgets/{id}",
        operation_id="widgets_delete",
        mcp=ir.McpMeta(
            name="delete", safety=ir.Safety.DESTRUCTIVE, title="Delete", documentation="Delete."
        ),
        tests=(case,),
    )
    res = ir.Resource(
        domain="tracker", resource="widgets", security="oauth_token", models=(), operations=(op,)
    )
    ctx = EmitContext(
        package_root="ycli.yandex.tracker",
        config=ir.ClientConfig(
            name="tracker", server=ir.Server(base_url="https://api.example"), auth=()
        ),
    )
    page = resolve.resolve_tests(res, ctx, NAMING, TYPE_MAPPER, DOCSTRINGS)
    assert not any(constant.startswith("_PAYLOAD_") for constant in page.constants)


def test_resolve_tests_raises_without_client_config(me_resource):
    ctx = EmitContext(package_root="ycli.yandex.tracker", config=None)
    with pytest.raises(ValueError, match="requires ClientConfig"):
        resolve.resolve_tests(me_resource, ctx, NAMING, TYPE_MAPPER, DOCSTRINGS)


def test_cli_test_raises_without_cli_facet(me_resource):
    op = me_resource.operations[0]
    case = next(c for c in op.tests if c.kind is ir.TestKind.CLI)
    bare_op = op.model_copy(update={"cli": None})
    with pytest.raises(ValueError, match="no cli facet"):
        resolve._cli_test(me_resource, bare_op, case)


def test_mcp_test_raises_without_mcp_facet(me_resource):
    op = me_resource.operations[0]
    case = next(c for c in op.tests if c.kind is ir.TestKind.MCP)
    bare_op = op.model_copy(update={"mcp": None})
    with pytest.raises(ValueError, match="no mcp facet"):
        resolve._mcp_test(me_resource, bare_op, case)


def test_guard_test_raises_without_mcp_facet(me_resource):
    op = me_resource.operations[0]
    case = next(c for c in op.tests if c.kind is ir.TestKind.MCP_GUARD)
    bare_op = op.model_copy(update={"mcp": None})
    with pytest.raises(ValueError, match="no mcp facet"):
        resolve._guard_test(me_resource, bare_op, case)


def test_select_scheme_raises_spec_error_for_unknown_security_name():
    config = ir.ClientConfig(name="x", server=ir.Server(base_url="https://x"), auth=())
    with pytest.raises(SpecError, match=r"nonexistent.*names no auth scheme"):
        resolve._select_scheme(config, "nonexistent")


def test_select_scheme_continues_past_non_matching_entries():
    """``config.auth`` with >1 entry: a non-matching earlier entry must not short-circuit the
    search - the loop continues until it finds the name that matches ``security``."""
    other = ir.HeaderAuth(header="X-Other", template="{tok}", inputs=(ir.AuthInput(name="tok"),))
    wanted = ir.HeaderAuth(
        header="Authorization", template="Bearer {token}", inputs=(ir.AuthInput(name="token"),)
    )
    config = ir.ClientConfig(
        name="x",
        server=ir.Server(base_url="https://x"),
        auth=(("other", other), ("oauth_token", wanted)),
    )
    assert resolve._select_scheme(config, "oauth_token") is wanted


def test_resolve_root_client_raises_without_client_config(me_resource):
    ctx = EmitContext(package_root="ycli.yandex.tracker", config=None)
    with pytest.raises(ValueError, match="requires ClientConfig"):
        resolve.resolve_root_client((me_resource,), ctx, NAMING, DOCSTRINGS)


def test_resolve_root_client_renders_single_header_auth(me_resource):
    """A HeaderAuth (single-header) scheme, not just MultiHeaderAuth, must resolve correctly."""
    ctx = EmitContext(
        package_root="ycli.yandex.tracker",
        config=ir.ClientConfig(
            name="tracker",
            server=ir.Server(base_url="https://api.tracker.yandex.net/v3"),
            auth=(
                (
                    "oauth_token",  # matches me_resource.security
                    ir.HeaderAuth(
                        header="Authorization",
                        template="Bearer {token}",
                        inputs=(ir.AuthInput(name="token", env="TOKEN"),),
                    ),
                ),
            ),
        ),
    )
    page = resolve.resolve_root_client((me_resource,), ctx, NAMING, DOCSTRINGS)
    init_method = page.methods[0]
    assert 'auth = HeaderAuth("Authorization", f"Bearer {token}")' in init_method
    assert "from .runtime.auth import HeaderAuth" in page.import_lines
