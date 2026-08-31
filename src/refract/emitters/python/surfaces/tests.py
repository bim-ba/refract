from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import EmitContext, SurfaceEmitter
from refract.emitters.python.resolve.tests import resolve_tests

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir


class TestsSurface(SurfaceEmitter):
    name = "tests"

    def __init__(self, env: Environment) -> None:
        self._env = env

    def applies(self, res: ir.Resource) -> bool:
        return any(op.tests for op in res.operations)

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        page = resolve_tests(res, ctx)
        return self._env.get_template("tests.jinja").render(page=page)
