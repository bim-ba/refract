import difflib
from pathlib import Path

from refract.emitters.python import client, models
from refract.emitters.python._common import render_doc

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def _diff(expected: str, actual: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            expected.splitlines(), actual.splitlines(), "golden", "emitted", lineterm=""
        )
    )


def test_priorities_client_emit_is_byte_identical_to_real_ycli(priorities_resource):
    golden = (_GOLDEN / "tracker" / "priorities" / "client.py").read_text(encoding="utf-8")
    emitted = client.emit(priorities_resource)
    assert emitted == golden, _diff(golden, emitted)


def test_me_client_emit_still_byte_identical(me_resource):
    """Regression anchor — the ``TypedModel`` split must not disturb the plain empty-body read."""
    golden = (_GOLDEN / "tracker" / "me" / "client.py").read_text(encoding="utf-8")
    emitted = client.emit(me_resource)
    assert emitted == golden, _diff(golden, emitted)


def test_priorities_models_emit_still_byte_identical(priorities_resource):
    """The ``render_doc`` consolidation must keep the multi-line model docstrings intact."""
    golden = (_GOLDEN / "tracker" / "priorities" / "models.py").read_text(encoding="utf-8")
    emitted = models.emit(priorities_resource)
    assert emitted == golden, _diff(golden, emitted)


def test_me_models_emit_still_byte_identical(me_resource):
    """The ``render_doc`` consolidation must keep the one-line model docstrings intact."""
    golden = (_GOLDEN / "tracker" / "me" / "models.py").read_text(encoding="utf-8")
    emitted = models.emit(me_resource)
    assert emitted == golden, _diff(golden, emitted)


def test_render_doc_returns_no_lines_for_absent_text():
    """An absent (``None`` / empty) docstring renders nothing — no dangling quote block."""
    assert render_doc(None, "    ") == []
    assert render_doc("", "    ") == []
