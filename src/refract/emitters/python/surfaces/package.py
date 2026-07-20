from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import EmitContext, SurfaceEmitter

if TYPE_CHECKING:
    from refract import ir


class PackageSurface(SurfaceEmitter):
    """The `__init__.py` surface: a package marker whose whole body is the resource docstring."""

    name = "package"

    def applies(self, res: ir.Resource) -> bool:
        return True

    def emit(self, res: ir.Resource, ctx: EmitContext) -> str:
        return f'"""{res.documentation}"""\n'
