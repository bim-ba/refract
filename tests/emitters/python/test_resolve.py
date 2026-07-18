import ast

import pytest

from refract import ir
from refract.emitters.api import EmitContext, Import
from refract.emitters.python import resolve
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.types import PythonTypeMapper
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


def test_model_field_with_alias_emits_field_alias():
    """`field.alias` must render `Field(alias=...)` even without a description."""
    field = ir.Field(name="type_", type=ir.ScalarType(scalar="string"), alias="type")
    decl, _imports = resolve._model_field(field, TYPE_MAPPER)
    ast.parse(f"class M:\n{decl}\n")  # must not raise SyntaxError
    assert 'alias="type"' in decl
    assert "Field(" in decl


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
