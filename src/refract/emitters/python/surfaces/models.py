from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve.models import resolve_models

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir


class ModelsSurface(SurfaceEmitter):
    name = "models"

    def __init__(self, env: Environment) -> None:
        self._env = env

    def applies(self, res: ir.Resource) -> bool:
        return bool(res.models)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_models(res, ctx)
        return self._env.get_template("models.jinja").render(page=page)
