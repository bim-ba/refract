"""Driver: render every ``resource.yaml`` under a specs dir into the ycli quartet + tests.

Mirrors ycli's real per-resource layout: the four surface files (``models.py``, ``client.py``,
``cli.py``, ``mcp.py``) plus the package ``__init__.py`` live under ``<out>/<domain>/<resource>/``;
the test file is rooted separately at ``<out>/tests/<domain>/test_<resource>.py`` — ycli's real
flat per-domain test layout (see ``tests/yandex/tracker/test_me.py`` upstream).

:func:`check` is the drift gate (mirrors ``scripts/gen_coverage.py --check`` in the real ycli
repo): it compares a freshly-rendered plan against whatever is currently on disk and reports every
file where the committed ``out/`` tree has diverged from its spec, so generated code can never
silently drift from its source of truth.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from refract.emitters.python import cli, client, mcp, models, tests
from refract.loader import load

if TYPE_CHECKING:
    from refract import ir

__all__ = ["check", "plan", "render_resource", "write"]


def render_resource(res: ir.Resource) -> dict[str, str]:
    """Every output file for one resource, keyed by path relative to the top-level ``out/`` dir.

    Data-presence surface-gating: ``__init__.py``, ``models.py`` and ``client.py`` are always
    emitted (a resource always has documentation, models, and operations); the remaining surfaces
    are gated on the resource actually carrying data for them — ``cli.py`` only when some operation
    has a ``cli`` facet, ``mcp.py`` only when some operation has an ``mcp`` facet, and the test file
    only when some operation authored ``tests``. So ``me`` (cli + mcp + tests facets) emits all six
    files while ``priorities`` (mcp facets only) emits exactly four.

    The always-on surfaces + the package ``__init__.py`` key under ``<domain>/<resource>/...``; the
    test file keys separately under ``tests/<domain>/test_<resource>.py``.
    """
    base = f"{res.domain}/{res.resource}"
    files = {
        f"{base}/__init__.py": f'"""{res.documentation}"""\n',
        f"{base}/models.py": models.emit(res),
        f"{base}/client.py": client.emit(res),
    }
    if any(op.cli is not None for op in res.operations):
        files[f"{base}/cli.py"] = cli.emit(res)
    if any(op.mcp is not None for op in res.operations):
        files[f"{base}/mcp.py"] = mcp.emit(res)
    if any(op.tests for op in res.operations):
        files[f"tests/{res.domain}/test_{res.resource}.py"] = tests.emit(res)
    return files


def plan(specs_dir: Path, out_dir: Path) -> dict[Path, str]:
    """Map every target file under ``out_dir`` to its freshly-rendered content.

    Every ``specs_dir/**/resource.yaml`` (sorted for determinism) is loaded and rendered via
    :func:`render_resource`; may raise :class:`refract.loader.SpecError` if any spec is invalid.
    """
    the_plan: dict[Path, str] = {}
    for spec_path in sorted(Path(specs_dir).glob("**/resource.yaml")):
        res = load(spec_path)
        for rel, content in render_resource(res).items():
            the_plan[Path(out_dir) / rel] = content
    return the_plan


def write(the_plan: dict[Path, str]) -> None:
    """Write every entry of ``the_plan`` to disk, creating parent directories as needed."""
    for path, content in the_plan.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _current(path: Path) -> str | None:
    """The current on-disk content of ``path``, or ``None`` if it doesn't exist yet."""
    return path.read_text(encoding="utf-8") if path.exists() else None


def check(the_plan: dict[Path, str]) -> int:
    """Return 0 if every file in ``the_plan`` matches what's on disk, else 1.

    On drift, prints the stale-file list to stderr (the same signal a CI drift gate reads).
    """
    stale = [path for path, content in the_plan.items() if _current(path) != content]
    if stale:
        print("out/ is stale; run: refract generate --write", file=sys.stderr)
        for path in stale:
            print(f"  drift: {path}", file=sys.stderr)
        return 1
    print(f"out/ is up to date ({len(the_plan)} files).", file=sys.stderr)
    return 0
