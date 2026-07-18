"""Whole-snapshot proof: every generated file under the committed L1 corpus
(``examples/ycli-tracker/out/``) is compilable Python.

``compile(..., "exec")`` compiles to bytecode without executing it, so this holds even though the
generated modules import ``ycli``/``uplink`` runtime packages that aren't installed here (imports
resolve only at run time). It is a strict superset of ``ast.parse``: besides the parse-level
``SyntaxError`` classes (a required parameter after a defaulted one, a stray relative import), it
also catches symbol-table ``SyntaxError``s that ``ast.parse`` silently admits - notably a
DUPLICATE function argument, which a cross-source param collision (a body option colliding with a
path/query param) would emit. It does NOT resolve imports or catch undefined names (those are
run-time ``NameError``s, gated by the resolver unit tests and the behavioral tier instead).
"""

from pathlib import Path

import pytest

_OUT = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "out"
_PY_FILES = sorted(_OUT.rglob("*.py"))


def test_out_tree_is_not_empty():
    # Guards the walk itself: an empty glob would make the parametrized test below vacuously pass.
    assert _PY_FILES


@pytest.mark.parametrize("path", _PY_FILES, ids=lambda p: str(p.relative_to(_OUT)))
def test_generated_file_is_compilable_python(path: Path):
    source = path.read_text(encoding="utf-8")
    compile(source, str(path), "exec")
