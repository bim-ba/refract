from pathlib import Path

from refract.emitters.python import client

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def test_client_emit_is_byte_identical_to_real_ycli(me_resource):
    golden = (_GOLDEN / "tracker" / "me" / "client.py").read_text(encoding="utf-8")
    assert client.emit(me_resource) == golden
