from __future__ import annotations

import builtins
import keyword

from refract.emitters.ports import Naming

# Names a Python identifier (def name OR parameter) would shadow (builtins + keywords).
_SHADOWED = frozenset(dir(builtins)) | frozenset(keyword.kwlist)


def _deconflict(name: str) -> str:
    """Suffix ``_`` to any identifier that shadows a builtin or keyword: ``list`` -> ``list_``,
    ``id`` -> ``id_``, ``class`` -> ``class_``; a safe name passes through unchanged."""
    return f"{name}_" if name in _SHADOWED else name


def _pascal(name: str) -> str:
    """``localized_name`` -> ``LocalizedName``. Private: only `class_name` reads it, so it is not
    part of the `Naming` port a backend implements."""
    return "".join(part.capitalize() for part in name.split("_"))


class PythonNaming(Naming):
    """Python identifier casing + shadow-guarding + class naming."""

    def identifier(self, name: str) -> str:
        return _deconflict(name)

    def class_name(self, base: str, suffix: str) -> str:
        return f"{_pascal(base)}{suffix}"

    def cli_option(self, parent: str, child: str) -> str:
        return f"{parent}_{child}"
