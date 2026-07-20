from refract.emitters.ports import LanguageBackend
from refract.emitters.python.backend import python_backend
from refract.emitters.registry import get_backend


def test_backend_composes_all_strategies_and_surfaces():
    b = python_backend()
    assert isinstance(b, LanguageBackend) and b.name == "python"
    assert {s.name for s in b.surfaces} == {
        "package",
        "models",
        "requests",
        "client",
        "cli",
        "mcp",
        "tests",
    }
    assert {s.name for s in b.domain_surfaces} == {"root_client", "shared_models"}  # per-API glue


def test_registered_and_resolvable():
    assert get_backend("python").name == "python"  # lazy import wires the registry
