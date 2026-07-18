from __future__ import annotations

import builtins
import keyword

from refract.emitters.api import Naming

# Names a module-level ``def`` would shadow (builtins + keywords).
_SHADOWED = frozenset(dir(builtins)) | frozenset(keyword.kwlist)


class PythonNaming(Naming):
    """Python identifier casing + shadow-guarding + class naming."""

    def pascal(self, name: str) -> str:
        return "".join(part.capitalize() for part in name.split("_"))

    def module_function(self, name: str) -> str:
        return f"{name}_" if name in _SHADOWED else name

    def class_name(self, base: str, suffix: str) -> str:
        return f"{self.pascal(base)}{suffix}"

    def cli_option(self, *parts: str) -> str:
        return "_".join(parts)
