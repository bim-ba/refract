from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.api import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve import resolve_requests

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.api import Docstrings, Naming, TypeMapper


class RequestsSurface(SurfaceEmitter):
    name = "requests"

    def __init__(self, naming: Naming, type_mapper: TypeMapper, docstrings: Docstrings,
                 env: Environment) -> None:
        self._naming, self._type_mapper, self._docstrings, self._env = (
            naming, type_mapper, docstrings, env)

    def applies(self, res: ir.Resource) -> bool:
        return bool(res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_requests(res, ctx, self._naming, self._type_mapper, self._docstrings)
        return self._env.get_template("requests.jinja").render(page=page)
