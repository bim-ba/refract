"""`github repos` commands."""

from __future__ import annotations

import typer
from ycli.cli.context import AppContext
from ycli.cli.output import Serializer
from ycli.yandex.github.repos.models import IssueCreate

app = typer.Typer(name="repos", help="GitHub repositories and their issues.", no_args_is_help=True)


@app.callback()
def _group() -> None:
    """Group anchor - forces subcommand dispatch (no eager DI, so --help stays cred-free)."""


@app.command()
def create(
    ctx: typer.Context,
    title: str,
    owner: str,
    repo: str,
    body: str | None = None,
    milestone: int | None = None,
) -> None:
    """Open an issue from a title and an optional body/milestone."""
    app_ctx = AppContext.from_typer_context(ctx)
    Serializer.serialize(
        app_ctx.github.repos.create_issue(
            owner, repo, IssueCreate(title=title, body=body, milestone=milestone)
        ),
        app_ctx.strategy,
        app_ctx.console,
    )
