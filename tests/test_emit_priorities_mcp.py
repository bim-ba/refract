import difflib
from pathlib import Path

from refract.emitters.python import mcp

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def _diff(expected: str, actual: str) -> str:
    return "\n".join(
        difflib.unified_diff(
            expected.splitlines(), actual.splitlines(), "golden", "emitted", lineterm=""
        )
    )


def test_priorities_mcp_emit_is_byte_identical_to_real_ycli(priorities_resource):
    """Multi-op module: RO read + WRITE/WRITE_IDEMPOTENT writes, typed bodies, no guard."""
    golden = (_GOLDEN / "tracker" / "priorities" / "mcp.py").read_text(encoding="utf-8")
    emitted = mcp.emit(priorities_resource)
    assert emitted == golden, _diff(golden, emitted)


def test_me_mcp_emit_still_byte_identical(me_resource):
    """Regression anchor — the single guarded reads-only tool stays identical."""
    golden = (_GOLDEN / "tracker" / "me" / "mcp.py").read_text(encoding="utf-8")
    emitted = mcp.emit(me_resource)
    assert emitted == golden, _diff(golden, emitted)
