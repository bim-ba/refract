from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import DomainEmitter, EmitContext
from refract.emitters.python.resolve.models import resolve_shared_models

if TYPE_CHECKING:
    from jinja2 import Environment

    from refract import ir


class SharedModelsSurface(DomainEmitter):
    """Per-domain glue: `_models.yaml` models emitted ONCE into `{domain}/shared_models.py`,
    imported cross-file by any consuming resource's `models.py` (`resolve_models`'s shared-import
    scan)."""

    name = "shared_models"

    def __init__(self, env: Environment) -> None:
        self._env = env

    def applies(self, resources: tuple[ir.Resource, ...]) -> bool:
        """False when the domain has no `_models.yaml` (`shared_models` empty) - no empty
        `shared_models.py` gets emitted (identical across the domain by Task 9's
        `_attach_shared`, so `resources[0]` stands in for the whole domain's)."""
        return bool(resources[0].shared_models)

    def emit(self, resources: tuple[ir.Resource, ...], ctx: EmitContext) -> str:
        page = resolve_shared_models(resources, ctx)
        return self._env.get_template("models.jinja").render(page=page)
