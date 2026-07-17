"""Emit ``cli.py`` — the typer command group (output ONLY via ``Serializer.serialize``, ARCH-4).

Reproduces the ycli CLI idioms for the ``me`` walking skeleton: a ``typer.Typer(...)`` group, a
``_group()`` callback anchor, and a param-less passthrough command that resolves
``AppContext.from_typer_context(ctx)`` and ends in ``Serializer.serialize(...)``. Commands that
take typer arguments/options (path/query/body params, paginated lists) arrive with the resources
that need them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.python._common import render_doc
from refract.format import ruff_format

if TYPE_CHECKING:
    from refract import ir

_GROUP_DOC = "Group anchor — forces subcommand dispatch (no eager DI, so --help stays cred-free)."


def _command(res: ir.Resource, operation: ir.Operation) -> list[str]:
    """One ``@app.command()`` passthrough command (param-less; serializes the client call)."""
    meta = operation.cli
    assert meta is not None  # every me operation carries a cli facet
    call = f"app_ctx.{res.domain}.{res.resource}.{operation.name}()"
    lines = [
        "@app.command()",
        f"def {meta.name}(ctx: typer.Context) -> None:",
    ]
    lines += render_doc(meta.documentation, "    ")
    lines += [
        "    app_ctx = AppContext.from_typer_context(ctx)",
        f"    Serializer.serialize({call}, app_ctx.strategy, app_ctx.console)",
    ]
    return lines


def emit(res: ir.Resource) -> str:
    """Render the whole ``cli.py`` for ``res`` (ruff-formatted)."""
    name = res.resource
    group_help = res.module_docs.cli_group_help
    group = f'app = typer.Typer(name="{name}", help="{group_help}", no_args_is_help=True)'
    out = [
        *render_doc(res.module_docs.cli, ""),
        "",
        "from __future__ import annotations",
        "",
        "import typer",
        "",
        "from ycli.cli.context import AppContext",
        "from ycli.cli.output import Serializer",
        "",
        group,
        "",
        "",
        "@app.callback()",
        "def _group() -> None:",
        f'    """{_GROUP_DOC}"""',
    ]
    for operation in res.operations:
        out += ["", "", *_command(res, operation)]
    rendered = "\n".join(out).rstrip() + "\n"
    return ruff_format(rendered)
