from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve import resolve_requests

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.ports import DocComments, Naming, TypeMapper


class RequestsSurface(SurfaceEmitter):
    name = "requests"

    def __init__(
        self, naming: Naming, type_mapper: TypeMapper, doc_comments: DocComments, env: Environment
    ) -> None:
        self._naming, self._type_mapper, self._doc_comments, self._env = (
            naming,
            type_mapper,
            doc_comments,
            env,
        )

    def applies(self, res: ir.Resource) -> bool:
        return bool(res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_requests(res, ctx, self._naming, self._type_mapper, self._doc_comments)
        return self._env.get_template("requests.jinja").render(page=page)
