from pathlib import Path

from refract.emitters.python import mcp

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def test_mcp_emit_is_byte_identical_to_real_ycli(me_resource):
    golden = (_GOLDEN / "tracker" / "me" / "mcp.py").read_text(encoding="utf-8")
    assert mcp.emit(me_resource) == golden
