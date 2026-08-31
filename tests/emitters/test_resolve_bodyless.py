from refract import ir
from refract.emitters.python.backend import python_backend
from refract.emitters.python.resolve.client import _client_method
from refract.emitters.python.resolve.requests import _request_function
from refract.ir.types import ScalarType

_CTX = python_backend().context("ycli.yandex.tracker")
_DELETE = ir.Operation(
    name="delete",
    method="DELETE",
    path="widget/{id}",
    operation_id="widget_delete",
    response_model=None,
    params=(ir.Param(name="id", loc="path", type=ScalarType(scalar="string")),),
)


def test_request_function_bodyless_returns_request_none():
    text, imports = _request_function(_DELETE, _CTX)
    assert "-> Request[None]:" in text
    assert "response_model=None" in text
    assert not any(imp.name == "None" for imp in imports)  # no `.models` import for None


def test_client_method_bodyless_returns_none():
    text, _ = _client_method(_DELETE, _CTX)
    assert "-> None:" in text
