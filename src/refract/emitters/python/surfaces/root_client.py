from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import DomainEmitter, EmitContext
from refract.emitters.python.resolve.root_client import resolve_root_client

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir


class RootClientSurface(DomainEmitter):
    """Per-API glue: the generated composition root aggregating all resources."""

    name = "root_client"

    def __init__(self, env: Environment) -> None:
        self._env = env

    def emit(self, resources: tuple[ir.Resource, ...], ctx: EmitContext) -> str:
        page = resolve_root_client(resources, ctx)
        return self._env.get_template("root_client.jinja").render(page=page)
