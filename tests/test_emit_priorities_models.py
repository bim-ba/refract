from pathlib import Path

from refract.emitters.python import models

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def test_priorities_models_emit_is_byte_identical_to_real_ycli(priorities_resource):
    golden = (_GOLDEN / "tracker" / "priorities" / "models.py").read_text(encoding="utf-8")
    assert models.emit(priorities_resource) == golden
