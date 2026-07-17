import importlib
from importlib.metadata import PackageNotFoundError

import refract


def test_version_is_read_from_metadata():
    # importlib.metadata.version("refract") for the installed dist; never the hardcoded "0.0.0".
    assert refract.__version__ != "0.0.0"
    assert refract.__version__  # non-empty string


def test_version_falls_back_when_package_not_installed(monkeypatch):
    """`importlib.metadata.version` raising PackageNotFoundError -> the "0.0.0+unknown" fallback."""

    def _raise(name: str) -> str:
        raise PackageNotFoundError(name)

    monkeypatch.setattr("importlib.metadata.version", _raise)
    try:
        importlib.reload(refract)
        assert refract.__version__ == "0.0.0+unknown"
    finally:
        monkeypatch.undo()
        importlib.reload(refract)  # restore the real installed-package version for other tests
