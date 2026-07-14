from pathlib import Path

from refract.emitters.python import models

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def test_models_emit_is_byte_identical_to_real_ycli(me_resource):
    golden = (_GOLDEN / "tracker" / "me" / "models.py").read_text(encoding="utf-8")
    assert models.emit(me_resource) == golden
