from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve import resolve_cli

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.api import Docstrings, Naming, TypeMapper


class CliSurface(SurfaceEmitter):
    name = "cli"

    def __init__(
        self, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings, env: Environment
    ) -> None:
        self._naming, self._type_mapper, self._docstrings, self._env = (
            naming,
            type_mapper,
            docstrings,
            env,
        )

    def applies(self, res: ir.Resource) -> bool:
        return any(op.cli is not None for op in res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_cli(res, ctx, self._naming, self._type_mapper, self._docstrings)
        return self._env.get_template("cli.jinja").render(page=page)
