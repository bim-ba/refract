import pytest

from refract import ir
from refract.emitters.api import EmitContext, Import
from refract.emitters.python import resolve
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.types import PythonTypeMapper

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


def test_select_scheme_raises_for_unknown_security_name():
    config = ir.ClientConfig(name="x", server=ir.Server(base_url="https://x"), auth=())
    with pytest.raises(KeyError):
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
