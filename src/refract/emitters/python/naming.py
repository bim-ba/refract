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


class PythonNaming(Naming):
    """Python identifier casing + shadow-guarding + class naming."""

    def pascal(self, name: str) -> str:
        return "".join(part.capitalize() for part in name.split("_"))

    def module_function(self, name: str) -> str:
        return _deconflict(name)

    def safe_param(self, name: str) -> str:
        return _deconflict(name)

    def class_name(self, base: str, suffix: str) -> str:
        return f"{self.pascal(base)}{suffix}"

    def cli_option(self, *parts: str) -> str:
        return "_".join(parts)
