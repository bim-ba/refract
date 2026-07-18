"""D1 (F2): `resolve_tests` must iterate ALL tests-bearing operations, not just the first.

Builds a synthetic two-operation Resource (modeled on the `me` fixture's `ir.TestCase` shape -
see examples/ycli-tracker/tracker/me/resource.yaml) where BOTH operations carry a client-kind
test case, and asserts both render with distinct, per-op `_URL_<op.name>` constants.
"""

from __future__ import annotations

import re

import pytest

from refract import ir
from refract.emitters.api import EmitContext
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.resolve import resolve_tests
from refract.emitters.python.types import PythonTypeMapper


def _client_case(op_name: str) -> ir.TestCase:
    return ir.TestCase(
        name=f"{op_name}_client",
        kind=ir.TestKind.CLIENT,
        http_method="GET",
        path=f"widgets/{op_name}",
        status=200,
        response_json={"id": 1},
        has_json=True,
        asserts=["isinstance(widget, Widget)"],
        call=f'WidgetClient(token="t").widgets.{op_name}()',
    )


def _op(name: str) -> ir.Operation:
    return ir.Operation(
        name=name,
        method="GET",
        path=f"widgets/{name}",
        operation_id=f"widgets_{name}",
        response_model="Widget",
        tests=(_client_case(name),),
    )


@pytest.fixture
def two_op_tested_resource() -> ir.Resource:
    return ir.Resource(
        domain="widget",
        resource="widgets",
        security="token",
        models=(),
        operations=(_op("first"), _op("second")),
    )


@pytest.fixture
def ctx() -> EmitContext:
    return EmitContext(
        package_root="ycli.widget.widgets",
        config=ir.ClientConfig(
            name="widget",
            server=ir.Server(base_url="https://api.widget.example"),
            auth=(),
        ),
    )


@pytest.fixture
def parts() -> tuple[PythonNaming, PythonTypeMapper, PythonDocstrings]:
    return PythonNaming(), PythonTypeMapper(), PythonDocstrings()


def test_resolve_tests_renders_all_tests_bearing_ops(two_op_tested_resource, ctx, parts):
    page = resolve_tests(two_op_tested_resource, ctx, *parts)
    names = list(page.tests)
    assert any("test_first" in t for t in names)
    assert any("test_second" in t for t in names)
    assert sum(c.startswith("_URL") for c in page.constants) == 2


def _write_op_with_nested_body() -> ir.Operation:
    """A write op whose body model has a nested `ref<...>` field - mirrors `PriorityCreate.name:
    ref<LocalizedName>` - so the literal test `call` constructs BOTH classes, e.g.
    `WidgetCreate(name=WidgetName(en="x"))`.
    """
    case = ir.TestCase(
        name="create_client",
        kind=ir.TestKind.CLIENT,
        http_method="POST",
        path="widgets",
        status=200,
        response_json={"id": 1},
        has_json=True,
        asserts=["isinstance(widget, Widget)"],
        call='WidgetClient(token="t").widgets.create(WidgetCreate(name=WidgetName(en="x")))',
    )
    return ir.Operation(
        name="create",
        method="POST",
        path="widgets",
        operation_id="widgets_create",
        body=ir.Body(model="WidgetCreate"),
        response_model="Widget",
        tests=(case,),
    )


@pytest.fixture
def write_op_resource() -> ir.Resource:
    return ir.Resource(
        domain="widget",
        resource="widgets",
        security="token",
        models=(
            ir.ObjectModel(
                name="WidgetCreate",
                fields=(ir.Field(name="name", type=ir.RefType(target="WidgetName")),),
            ),
        ),
        operations=(_write_op_with_nested_body(),),
    )


def test_resolve_tests_client_write_op_imports_body_and_nested_ref_models(
    write_op_resource, ctx, parts
):
    """A CLIENT-kind test on a write op must import the body model (`op.body.model`) AND any
    directly-nested `ref<...>` field of that body model - both classes appear literally in the
    authored `call` string, so both need a `from ...models import ...` line or the generated test
    module is invalid Python (NameError at import/run time).
    """
    page = resolve_tests(write_op_resource, ctx, *parts)
    # ctx.package_root ("ycli.widget.widgets") + res.resource ("widgets") - matches the shared
    # `ctx` fixture above, which already ends in the resource segment. `Widget` (the response
    # model) shares the same module, so it merges into the same grouped import line.
    model_import = "from ycli.widget.widgets.widgets.models import Widget, WidgetCreate, WidgetName"
    assert model_import in page.import_lines


def _cli_only_op() -> ir.Operation:
    """An op whose ONLY test case is CLI-kind (no CLIENT case). `_stub` references
    `_PAYLOAD_<op>` for every non-guard case, so the payload constant must still be emitted -
    otherwise the generated CLI test raises `NameError` on an undefined `_PAYLOAD_get`.
    """
    case = ir.TestCase(
        name="get_cli",
        kind=ir.TestKind.CLI,
        http_method="GET",
        path="widgets",
        status=200,
        response_json={"id": 1},
        has_json=True,
        asserts=["res.exit_code == 0"],
        call="",
    )
    return ir.Operation(
        name="get",
        method="GET",
        path="widgets",
        operation_id="widgets_get",
        response_model="Widget",
        cli=ir.CliMeta(name="get", documentation="Get a widget."),
        tests=(case,),
    )


@pytest.fixture
def cli_only_resource() -> ir.Resource:
    return ir.Resource(
        domain="widget",
        resource="widgets",
        security="token",
        models=(),
        operations=(_cli_only_op(),),
    )


def test_resolve_tests_cli_only_op_defines_referenced_payload(cli_only_resource, ctx, parts):
    """C1 regression: every `_PAYLOAD_<op>` a test body references must be defined as a module
    constant. A cli-only (no CLIENT-case) op still stubs via `_PAYLOAD_get`, so the constant
    must be emitted; the pre-fix emitter gated it on `TestKind.CLIENT` and left it undefined.
    """
    page = resolve_tests(cli_only_resource, ctx, *parts)
    defined = set(re.findall(r"^(_PAYLOAD_\w+) =", "\n".join(page.constants), re.MULTILINE))
    referenced = set(re.findall(r"_PAYLOAD_\w+", "\n".join(page.tests)))
    assert referenced <= defined, f"undefined payload constants: {referenced - defined}"
