from pathlib import Path

import pytest

from refract.generation import Generator

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
_CORPUS = sorted(path for path in _EXAMPLES.iterdir() if path.is_dir())

# (path under out/, class, auth mechanism) per example - enumerated so a new example must register
# here rather than be silently skipped by the directory walk.
_ROOT_CLIENT_GOLDEN = {
    "ycli-tracker": ("tracker/client.py", "TrackerClient", "MultiHeaderAuth"),
    "github": ("github/client.py", "GithubClient", "HeaderAuth"),
}


def test_every_example_is_registered():
    # Guards both walks: an empty or unregistered corpus would make the tests below vacuous.
    assert {path.name for path in _CORPUS} == set(_ROOT_CLIENT_GOLDEN)


@pytest.mark.parametrize("example", _CORPUS, ids=lambda path: path.name)
def test_committed_out_matches_fresh_render(example: Path):
    # The committed out/ tree IS the L1 snapshot: it must equal a fresh render (no drift).
    g = Generator.for_language("python")
    assert g.check(g.plan(example, example / "out")) == 0


@pytest.mark.parametrize("example", _CORPUS, ids=lambda path: path.name)
def test_root_client_golden_committed(example: Path):
    # the per-API root client is part of the committed L1 corpus (§C DomainEmitter / §F target)
    relative, client_class, mechanism = _ROOT_CLIENT_GOLDEN[example.name]
    root = (example / "out" / relative).read_text(encoding="utf-8")
    assert f"class {client_class}" in root and mechanism in root
