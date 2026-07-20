from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import DomainEmitter, EmitContext
from refract.emitters.python.resolve import resolve_root_client

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir
    from refract.emitters.ports import DocComments, Naming, TypeMapper


class RootClientSurface(DomainEmitter):
    """Per-API glue: the generated composition root aggregating all resources."""

    name = "root_client"

    def __init__(
        self, naming: Naming, type_mapper: TypeMapper, doc_comments: DocComments, env: Environment
    ) -> None:
        self._naming, self._type_mapper, self._doc_comments, self._env = (
            naming,
            type_mapper,
            doc_comments,
            env,
        )

    def emit(self, resources: tuple[ir.Resource, ...], ctx: EmitContext) -> str:
        page = resolve_root_client(resources, ctx, self._naming, self._doc_comments)
        return self._env.get_template("root_client.jinja").render(page=page)
