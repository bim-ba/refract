from refract import ir
from refract.emitters.python.doc_comments import PythonDocComments
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.resolve import _client_method, _request_function
from refract.emitters.python.types import PythonTypeMapper
from refract.ir.types import ScalarType

_PARTS = (PythonNaming(), PythonTypeMapper(), PythonDocComments())
_DELETE = ir.Operation(
    name="delete",
    method="DELETE",
    path="widget/{id}",
    operation_id="widget_delete",
    response_model=None,
    params=(ir.Param(name="id", loc="path", type=ScalarType(scalar="string")),),
)


def test_request_function_bodyless_returns_request_none():
    text, imports = _request_function(_DELETE, *_PARTS)
    assert "-> Request[None]:" in text
    assert "response_model=None" in text
    assert not any(imp.name == "None" for imp in imports)  # no `.models` import for None


def test_client_method_bodyless_returns_none():
    text, _ = _client_method(_DELETE, *_PARTS)
    assert "-> None:" in text
