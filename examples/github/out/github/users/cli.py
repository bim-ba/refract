"""`github users` commands."""

from __future__ import annotations

import typer
from ycli.cli.context import AppContext
from ycli.cli.output import Serializer

app = typer.Typer(name="users", help="GitHub user accounts.", no_args_is_help=True)


@app.callback()
def _group() -> None:
    """Group anchor - forces subcommand dispatch (no eager DI, so --help stays cred-free)."""


@app.command()
def me(ctx: typer.Context) -> None:
    """Print the authenticated user (a safe auth probe)."""
    app_ctx = AppContext.from_typer_context(ctx)
    Serializer.serialize(app_ctx.github.users.me(), app_ctx.strategy, app_ctx.console)
