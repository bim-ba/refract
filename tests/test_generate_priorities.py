"""Data-presence surface-gating: ``priorities`` graduates into the globbed tree with 4 surfaces.

``render_resource`` emits only the surfaces a resource carries data for. ``priorities`` authored
``mcp:`` facets but no ``cli:`` facets and no ``tests:``, so it renders exactly four files
(``__init__``, ``models``, ``client``, ``mcp``) — no ``cli.py``, no test file. ``me`` (which does
carry cli + tests facets) still renders all six, so the gating never regressed the walking skeleton.
"""

from pathlib import Path

from refract.generate import render_resource

_GOLDEN = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker" / "golden"


def test_priorities_renders_exactly_four_gated_surfaces(priorities_resource):
    files = render_resource(priorities_resource)
    assert set(files) == {
        "tracker/priorities/__init__.py",
        "tracker/priorities/models.py",
        "tracker/priorities/client.py",
        "tracker/priorities/mcp.py",
    }
    for rel, content in files.items():
        assert content == (_GOLDEN / rel).read_text("utf-8"), rel


def test_me_still_renders_all_six_surfaces(me_resource):
    # Regression: surface-gating must not drop me's cli.py or its test file.
    assert set(render_resource(me_resource)) == {
        "tracker/me/__init__.py",
        "tracker/me/models.py",
        "tracker/me/client.py",
        "tracker/me/cli.py",
        "tracker/me/mcp.py",
        "tests/tracker/test_me.py",
    }
