from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from refract.emitters.api import LanguageBackend

__all__ = ["UnknownBackendError", "backend", "get_backend"]

_BACKENDS: dict[str, Callable[[], LanguageBackend]] = {}


class UnknownBackendError(Exception):
    """No backend registered (and none importable) under this language name."""


def backend(name: str) -> Callable[[Callable[[], LanguageBackend]], Callable[[], LanguageBackend]]:
    """Register a LanguageBackend factory under ``name`` (used as ``@backend("python")``)."""

    def register(factory: Callable[[], LanguageBackend]) -> Callable[[], LanguageBackend]:
        _BACKENDS[name] = factory
        return factory

    return register


def get_backend(name: str) -> LanguageBackend:
    """Resolve a backend, lazily importing ``refract.emitters.<name>.backend`` on first use."""
    if name not in _BACKENDS:
        try:
            importlib.import_module(f"refract.emitters.{name}.backend")
        except ModuleNotFoundError as error:
            raise UnknownBackendError(f"no backend for language {name!r}") from error
    if name not in _BACKENDS:
        raise UnknownBackendError(
            f"module refract.emitters.{name}.backend did not register {name!r}"
        )
    return _BACKENDS[name]()
