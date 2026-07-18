import pytest

from refract.emitters import registry


def test_register_and_get(monkeypatch):
    monkeypatch.setattr(registry, "_BACKENDS", {})
    marker = object()

    @registry.backend("toy")
    def _factory():
        return marker

    assert registry.get_backend("toy") is marker


def test_unknown_backend_raises(monkeypatch):
    monkeypatch.setattr(registry, "_BACKENDS", {})
    with pytest.raises(registry.UnknownBackendError):
        registry.get_backend("nope")  # lazy import of refract.emitters.nope.backend fails


def test_backend_module_imports_but_registers_nothing_raises(monkeypatch):
    monkeypatch.setattr(registry, "_BACKENDS", {})
    monkeypatch.setattr(registry.importlib, "import_module", lambda name: None)
    with pytest.raises(registry.UnknownBackendError, match="did not register"):
        registry.get_backend("silent")
