from refract import ir
from refract.emitters.python.layout import PythonLayout

lay = PythonLayout()
_res = ir.Resource(domain="tracker", resource="me", security="s", models=(), operations=())


def test_surface_paths():
    assert lay.path(_res, "requests") == "tracker/me/_requests.py"
    assert lay.path(_res, "client") == "tracker/me/client.py"
    assert lay.path(_res, "models") == "tracker/me/models.py"
    assert lay.path(_res, "mcp") == "tracker/me/mcp.py"
    assert lay.path(_res, "package") == "tracker/me/__init__.py"
    assert lay.path(_res, "tests") == "tests/tracker/test_me.py"
    assert lay.path(_res, "shared_models") == "tracker/shared_models.py"
