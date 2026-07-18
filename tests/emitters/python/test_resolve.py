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


def _op(**overrides) -> ir.Operation:
    fields = {
        "name": "get",
        "method": "GET",
        "path": "p",
        "operation_id": "get",
        "response_model": "Thing",
    }
    fields.update(overrides)
    return ir.Operation(**fields)


def test_request_function_raises_without_response_model():
    op = _op(response_model=None)
    with pytest.raises(ValueError, match="no response model"):
        resolve._request_function(op, NAMING, TYPE_MAPPER, DOCSTRINGS)


def test_client_method_raises_without_response_model():
    op = _op(response_model=None)
    with pytest.raises(ValueError, match="no response model"):
        resolve._client_method(op, NAMING, TYPE_MAPPER, DOCSTRINGS)


def test_cli_command_raises_without_cli_facet(me_resource):
    op = me_resource.operations[0].model_copy(update={"cli": None})
    with pytest.raises(ValueError, match="no cli facet"):
        resolve._cli_command(me_resource, op, DOCSTRINGS)


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
