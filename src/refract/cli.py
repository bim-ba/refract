"""The ``refract`` console-script entry point (Typer)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from refract.generation import Generator, find_client_config
from refract.spec import SpecError

app = typer.Typer(name="refract", no_args_is_help=True, add_completion=False)

_EXAMPLES = Path(__file__).resolve().parent.parent.parent / "examples" / "ycli-tracker"


@app.callback()
def main() -> None:
    """refract: spec-driven client/CLI/MCP generator."""
    # A Typer app with exactly one command auto-collapses so bare invocation runs it directly;
    # this empty callback forces group mode so `refract` (no subcommand) shows help instead.


@app.command()
def generate(
    write: Annotated[bool, typer.Option("--write", help="write rendered files to out/")] = False,
    check: Annotated[
        bool, typer.Option("--check", help="exit 1 if any out/ file is stale")
    ] = False,
    out: Annotated[Path, typer.Option("--out", help="output root")] = _EXAMPLES / "out",
    specs: Annotated[Path, typer.Option("--specs", help="specs root")] = _EXAMPLES,
    client: Annotated[
        Path | None,
        typer.Option("--client", help="per-API client.yaml (default: located under --specs)"),
    ] = None,
    lang: Annotated[str, typer.Option("--lang", help="target backend language")] = "python",
) -> None:
    """Render every resource.yaml under --specs (+ its client.yaml glue) into --out for --lang."""
    generator = Generator.for_language(lang)
    try:
        client_config = client or find_client_config(specs)
        the_plan = generator.plan(specs, out, client_config)
    except SpecError as error:
        typer.echo(f"spec error: {error}", err=True)
        raise typer.Exit(2) from error
    if write:
        generator.write(the_plan)
        typer.echo(f"wrote {len(the_plan)} files.")
        return
    if check:
        raise typer.Exit(generator.check(the_plan))
    for path in the_plan:
        typer.echo(f"would render {path}")
