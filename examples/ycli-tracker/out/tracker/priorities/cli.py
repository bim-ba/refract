"""`tracker priorities` commands."""

from __future__ import annotations

import typer
from ycli.cli.context import AppContext
from ycli.cli.output import Serializer
from ycli.yandex.tracker.priorities.models import LocalizedName, PriorityCreate, PriorityUpdate

app = typer.Typer(name="priorities", help="Tracker issue priorities.", no_args_is_help=True)


@app.callback()
def _group() -> None:
    """Group anchor - forces subcommand dispatch (no eager DI, so --help stays cred-free)."""


@app.command()
def create(
    ctx: typer.Context,
    key: str,
    name_ru: str | None = None,
    name_en: str | None = None,
    order: int | None = None,
    description: str | None = None,
) -> None:
    """Create a priority from a key, localized name, and optional order/description."""
    app_ctx = AppContext.from_typer_context(ctx)
    Serializer.serialize(
        app_ctx.tracker.priorities.create(
            PriorityCreate(
                key=key,
                name=LocalizedName(ru=name_ru, en=name_en),
                order=order,
                description=description,
            )
        ),
        app_ctx.strategy,
        app_ctx.console,
    )


@app.command()
def edit(
    ctx: typer.Context,
    priority_id: str,
    name_ru: str | None = None,
    name_en: str | None = None,
    description: str | None = None,
    version: int | None = None,
) -> None:
    """Edit a priority's name and/or description; pass version for optimistic locking."""
    app_ctx = AppContext.from_typer_context(ctx)
    Serializer.serialize(
        app_ctx.tracker.priorities.edit(
            priority_id,
            PriorityUpdate(name=LocalizedName(ru=name_ru, en=name_en), description=description),
            version=version,
        ),
        app_ctx.strategy,
        app_ctx.console,
    )
