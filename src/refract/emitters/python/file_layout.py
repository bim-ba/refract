from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.ports import FileLayout

if TYPE_CHECKING:
    from refract import ir

_FILENAME = {
    "requests": "_requests",
    "client": "client",
    "models": "models",
    "cli": "cli",
    "mcp": "mcp",
}


class PythonFileLayout(FileLayout):
    """Map (resource, surface) -> emitted file path (decouples surface id from filename)."""

    def path(self, res: ir.Resource, surface: str) -> str:
        base = f"{res.domain}/{res.resource}"
        if surface == "root_client":  # per-API domain surface (DomainEmitter)
            return f"{res.domain}/client.py"
        if surface == "shared_models":  # per-API domain surface (DomainEmitter)
            return f"{res.domain}/shared_models.py"
        if surface == "tests":
            return f"tests/{res.domain}/test_{res.resource}.py"
        if surface == "package":
            return f"{base}/__init__.py"
        return f"{base}/{_FILENAME[surface]}.py"
