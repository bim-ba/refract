from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve.cli import resolve_cli

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir


class CliSurface(SurfaceEmitter):
    name = "cli"

    def __init__(self, env: Environment) -> None:
        self._env = env

    def applies(self, res: ir.Resource) -> bool:
        return any(op.cli is not None for op in res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_cli(res, ctx)
        return self._env.get_template("cli.jinja").render(page=page)
