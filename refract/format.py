"""Post-emit formatting: pipe emitted source through ``ruff format`` (refract's own config).

Emitters produce structurally-correct source; ruff is the single authority on wrapping and
spacing, so output matches any ruff-formatted codebase (here: ycli) exactly. Never hand-emulate.
"""

from __future__ import annotations

import subprocess


def ruff_format(source: str) -> str:
    """Return ``source`` formatted by ``ruff format`` (reads stdin, writes stdout)."""
    result = subprocess.run(
        ["ruff", "format", "-"],
        input=source,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout
