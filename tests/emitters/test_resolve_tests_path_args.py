"""Issue #17: the generated test's mocked URL must carry SUBSTITUTED path values.

``_URL_<op>`` used to be ``base_url + op.path`` verbatim, so an operation whose path holds a
``{placeholder}`` stubbed a URL with literal braces - a URL the generated client can never
request. The mock URL is now built from ``path_template`` (the same helper the client's request
f-string is built from) formatted with the test case's ``path_args``, so the two can not drift.
"""

from __future__ import annotations

import pytest

from refract import ir
from refract.emitters.ports import EmitContext
from refract.emitters.python.doc_comments import PythonDocComments
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.resolve import resolve_tests
from refract.emitters.python.types import PythonTypeMapper

CTX = EmitContext(
    package_root="ycli.widget.widgets",
    config=ir.ClientConfig(
        name="widget", server=ir.Server(base_url="https://api.widget.example"), auth=()
    ),
)
PARTS = (PythonNaming(), PythonTypeMapper(), PythonDocComments())


def _resource(op: ir.Operation) -> ir.Resource:
    return ir.Resource(
        domain="widget", resource="widgets", security="token", models=(), operations=(op,)
    )


def _op(path: str, param_names: tuple[str, ...], path_args: tuple[tuple[str, str], ...]):
    case = ir.TestCase(
        name="get_client",
        kind=ir.TestKind.CLIENT,
        http_method="GET",
        path_args=path_args,
        status=200,
        response_json={"id": 1},
        has_json=True,
        asserts=["isinstance(widget, Widget)"],
        call='WidgetClient(token="t").widgets.get("W-1")',
    )
    return ir.Operation(
        name="get",
        method="GET",
        path=path,
        operation_id="widgets_get",
        params=tuple(
            ir.Param(name=name, loc="path", type=ir.ScalarType(scalar="string"))
            for name in param_names
        ),
        response_model="Widget",
        tests=(case,),
    )


def test_shadowed_path_param_value_reaches_the_mock_url():
    """``{id}`` binds the guarded identifier ``id_`` in the client's f-string; the mocked URL
    must still carry the VALUE, not either spelling of the name."""
    page = resolve_tests(_resource(_op("widgets/{id}", ("id",), (("id", "W-1"),))), CTX, *PARTS)
    assert '_URL_get = "https://api.widget.example/widgets/W-1"' in page.constants


def test_several_placeholders_substitute_independently():
    op = _op(
        "widgets/{widget_id}/parts/{part_id}",
        ("widget_id", "part_id"),
        (("widget_id", "W-1"), ("part_id", "7")),
    )
    page = resolve_tests(_resource(op), CTX, *PARTS)
    assert '_URL_get = "https://api.widget.example/widgets/W-1/parts/7"' in page.constants


def test_placeholderless_path_is_unchanged():
    """Regression control: the corpus shape (no placeholder, no args) renders as before."""
    page = resolve_tests(_resource(_op("widgets", (), ())), CTX, *PARTS)
    assert '_URL_get = "https://api.widget.example/widgets"' in page.constants


def test_missing_path_arg_fails_loud():
    """The loader rejects this at the boundary; IR from any other producer must not silently
    emit a brace-bearing URL either."""
    op = _op("widgets/{widget_id}", ("widget_id",), ())
    with pytest.raises(ValueError, match=r"test 'get_client'.*no value for path param 'widget_id'"):
        resolve_tests(_resource(op), CTX, *PARTS)
