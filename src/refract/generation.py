"""The language-agnostic driver: resolve a backend, render each resource's gated surfaces,
then the per-API domain glue (root client) once over all of the domain's resources."""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

from refract.emitters.ports import EmitContext
from refract.emitters.registry import get_backend
from refract.spec import SpecError, SpecLoader

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.ports import LanguageBackend

__all__ = ["Generator", "find_client_config", "find_shared_models"]


def _package_root(res: ir.Resource) -> str:
    """Where the generated code's runtime/base/models live (ycli convention by default)."""
    return f"ycli.yandex.{res.domain}"


def find_client_config(specs_dir: Path) -> Path:
    """Locate the per-API client.yaml sibling of / above the resource specs."""
    matches = sorted(Path(specs_dir).glob("**/client.yaml"))
    if not matches:
        raise SpecError(f"no client.yaml found under {specs_dir}")
    return matches[0]


def find_shared_models(specs_dir: Path) -> Path | None:
    """Locate the per-API `_models.yaml` sibling of / above the resource specs. Optional: `None`
    means no models are shared across the API's resources."""
    matches = sorted(Path(specs_dir).glob("**/_models.yaml"))
    if not matches:
        return None
    return matches[0]


def _attach_shared(res: ir.Resource, shared: tuple[ir.Model, ...]) -> ir.Resource:
    """Fail-loud (fork D): a model name defined in BOTH the resource's local `models:` and
    `_models.yaml` is rejected eagerly at plan time - `Resource.model()` never has to arbitrate."""
    collisions = {m.name for m in res.models} & {m.name for m in shared}
    if collisions:
        raise SpecError(
            f"{res.resource}: model name(s) {sorted(collisions)} defined both locally and in "
            "_models.yaml"
        )
    _reject_shared_as_body_or_response(res, {m.name for m in shared})
    return res.model_copy(update={"shared_models": shared})


def _reject_shared_as_body_or_response(res: ir.Resource, shared_names: set[str]) -> None:
    """Fail-loud (P1 scope): a shared model is supported as an EMBEDDED field of a local model (its
    `models.py` imports it cross-file), but NOT directly as an operation's request body or response
    model. In those positions requests/client/mcp/tests import the model by name from the LOCAL
    `.models` module, so a shared model would dangle at import time. Supporting a shared body/
    response model is deferred; reject rather than emit unimportable code. (A shared model reached
    THROUGH a local body model's field IS handled - see resolve/cli + resolve/tests.)"""
    if not shared_names:
        return
    for op in res.operations:
        if op.response_model in shared_names:
            raise SpecError(
                f"{res.resource}: operation {op.name!r} returns shared model "
                f"{op.response_model!r} - a shared model cannot be an operation's response model; "
                "embed it as a field of a local model instead"
            )
        if op.body is not None and op.body.model in shared_names:
            raise SpecError(
                f"{res.resource}: operation {op.name!r} takes shared model {op.body.model!r} as "
                "its request body - a shared model cannot be a body model; embed it in a local "
                "model instead"
            )


class Generator:
    """Orchestrates spec -> per-surface output for one backend. Never names a surface directly."""

    def __init__(self, backend: LanguageBackend) -> None:
        self._backend = backend

    @classmethod
    def for_language(cls, lang: str) -> Generator:
        return cls(get_backend(lang))

    def render_resource(self, res: ir.Resource, config: ir.ClientConfig) -> dict[str, str]:
        ctx = EmitContext(package_root=_package_root(res), config=config)
        files: dict[str, str] = {}
        for surface in self._backend.surfaces:
            if surface.applies(res):
                path = self._backend.file_layout.path(res, surface.name)
                files[path] = self._backend.formatter.format(surface.emit(res, ctx))
        return files

    def render_domain(
        self, resources: tuple[ir.Resource, ...], config: ir.ClientConfig
    ) -> dict[str, str]:
        """Run each domain surface ONCE over ALL of the domain's resources (root client)."""
        ctx = EmitContext(package_root=_package_root(resources[0]), config=config)
        files: dict[str, str] = {}
        for surface in self._backend.domain_surfaces:
            if surface.applies(resources):
                path = self._backend.file_layout.path(resources[0], surface.name)
                files[path] = self._backend.formatter.format(surface.emit(resources, ctx))
        return files

    def plan(
        self, specs_dir: Path, out_dir: Path, client_config: Path | None = None
    ) -> dict[Path, str]:
        config = SpecLoader.load_client_config(client_config or find_client_config(specs_dir))
        shared_models_path = find_shared_models(specs_dir)
        if shared_models_path is None:
            shared: tuple[ir.Model, ...] = ()
        else:
            shared = SpecLoader.load_shared_models(shared_models_path)
        by_domain: dict[str, list[ir.Resource]] = defaultdict(list)
        the_plan: dict[Path, str] = {}
        for spec_path in sorted(Path(specs_dir).glob("**/resource.yaml")):
            res = _attach_shared(SpecLoader.load(spec_path), shared)
            by_domain[res.domain].append(res)
            for rel, content in self.render_resource(res, config).items():
                the_plan[Path(out_dir) / rel] = content
        for resources in by_domain.values():  # per-API glue: root client, once per domain
            for rel, content in self.render_domain(tuple(resources), config).items():
                the_plan[Path(out_dir) / rel] = content
        return the_plan

    @staticmethod
    def write(the_plan: dict[Path, str]) -> None:
        for path, content in the_plan.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    @staticmethod
    def check(the_plan: dict[Path, str]) -> int:
        stale = [
            path
            for path, content in the_plan.items()
            if (path.read_text(encoding="utf-8") if path.exists() else None) != content
        ]
        if stale:
            print("out/ is stale; run: refract generate --write", file=sys.stderr)
            for path in stale:
                print(f"  drift: {path}", file=sys.stderr)
            return 1
        print(f"out/ is up to date ({len(the_plan)} files).", file=sys.stderr)
        return 0
