from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve.client import resolve_client

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir


class ClientSurface(SurfaceEmitter):
    name = "client"

    def __init__(self, env: Environment) -> None:
        self._env = env

    def applies(self, res: ir.Resource) -> bool:
        return bool(res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_client(res, ctx)
        return self._env.get_template("client.jinja").render(page=page)
