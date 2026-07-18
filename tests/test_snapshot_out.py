from pathlib import Path

from refract.generation import Generator

_EX = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


def test_committed_out_matches_fresh_render():
    # The committed out/ tree IS the L1 snapshot: it must equal a fresh render (no drift).
    g = Generator.for_language("python")
    assert g.check(g.plan(_EX, _EX / "out")) == 0


def test_root_client_golden_committed():
    # the per-API root client is part of the committed L1 corpus (§C DomainEmitter / §F target)
    root = (_EX / "out" / "tracker" / "client.py").read_text(encoding="utf-8")
    assert "class TrackerClient" in root and "MultiHeaderAuth" in root
