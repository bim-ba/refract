from pathlib import Path

from refract.emitters.python import cli

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def test_cli_emit_is_byte_identical_to_real_ycli(me_resource):
    golden = (_GOLDEN / "tracker" / "me" / "cli.py").read_text(encoding="utf-8")
    assert cli.emit(me_resource) == golden
