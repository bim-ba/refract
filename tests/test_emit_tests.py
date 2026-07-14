from pathlib import Path

from refract.emitters.python import tests

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def test_tests_emit_is_byte_identical_to_real_ycli(me_resource):
    golden = (_GOLDEN / "tests" / "tracker" / "test_me.py").read_text(encoding="utf-8")
    assert tests.emit(me_resource) == golden
