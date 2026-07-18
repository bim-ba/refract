import pytest

from refract.emitters.python import format as format_module
from refract.emitters.python.format import RuffFormatter

f = RuffFormatter()


def test_formats_via_ruff():
    assert f.format("x=1\ny  =  2\n") == "x = 1\ny = 2\n"


def test_reformats_dict_spacing():
    assert f.format('d={ "a":1 }\n') == 'd = {"a": 1}\n'


def test_sorts_imports():
    src = "from .models import Me\nimport typer\n\n\ndef f():\n    return (typer, Me)\n"
    out = f.format(src)
    assert out.index("import typer") < out.index("from .models import Me")


def test_syntax_error_raises_runtime_error():
    with pytest.raises(RuntimeError):
        f.format("def (:\n")  # invalid syntax -> ruff exits non-zero


def test_ruff_missing_from_path_raises_runtime_error(monkeypatch):
    def _raise(*args, **kwargs):
        raise FileNotFoundError("ruff")

    monkeypatch.setattr(format_module.subprocess, "run", _raise)
    with pytest.raises(RuntimeError, match="ruff not found on PATH"):
        f.format("x = 1\n")
