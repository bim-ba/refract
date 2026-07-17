"""The ``refract`` console-script entry point (Typer). Full wiring lands in Phase 8."""

from __future__ import annotations

import typer

app = typer.Typer(name="refract", no_args_is_help=True, add_completion=False)


@app.command()
def generate() -> None:
    """Render every resource spec into its per-(surface) output (not yet wired)."""
    raise NotImplementedError("refract generate is being rebuilt (Workstream A, Phase 8)")
