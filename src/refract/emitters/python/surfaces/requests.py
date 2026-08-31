from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve.requests import resolve_requests

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir


class RequestsSurface(SurfaceEmitter):
    name = "requests"

    def __init__(self, env: Environment) -> None:
        self._env = env

    def applies(self, res: ir.Resource) -> bool:
        return bool(res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_requests(res, ctx)
        return self._env.get_template("requests.jinja").render(page=page)
