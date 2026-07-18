"""Whole-snapshot proof: every generated file under the committed L1 corpus
(``examples/ycli-tracker/out/``) is syntactically valid Python.

``ast.parse`` checks syntax only (no import resolution), so this holds even though the generated
modules import ``ycli``/``uplink`` runtime packages that aren't installed here - it's a cheap,
strong oracle against a real regression class: a resolver emitting a required parameter after a
defaulted one (a ``SyntaxError``), a stray relative import, or any other malformed source that a
byte-equality snapshot test wouldn't itself catch if the golden were ever regenerated wrong.
"""

import ast
from pathlib import Path

import pytest

_OUT = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "out"
_PY_FILES = sorted(_OUT.rglob("*.py"))


def test_out_tree_is_not_empty():
    # Guards the walk itself: an empty glob would make the parametrized test below vacuously pass.
    assert _PY_FILES


@pytest.mark.parametrize("path", _PY_FILES, ids=lambda p: str(p.relative_to(_OUT)))
def test_generated_file_is_valid_python(path: Path):
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=str(path))
