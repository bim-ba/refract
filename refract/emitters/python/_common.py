"""Shared naming + formatting helpers for the Python emitters (no IR-shape logic here)."""

from __future__ import annotations

import builtins
import keyword
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from refract import ir

# Names a module-level ``def`` would shadow at module scope — Python builtins (``list``) and
# keywords (``import``). An operation named after one takes a trailing underscore (PEP 8).
_SHADOWED_NAMES = frozenset(dir(builtins)) | frozenset(keyword.kwlist)


def pascal(name: str) -> str:
    """``snake_case`` -> ``PascalCase`` (``comments`` -> ``Comments``, ``me`` -> ``Me``)."""
    return "".join(part.capitalize() for part in name.split("_"))


def function_name(name: str) -> str:
    """``operation.name`` as a safe module-level ``def`` identifier (``list`` -> ``list_``).

    A ``def`` binds its name at module scope, so an operation named after a Python builtin or
    keyword (``list``) would shadow it there; those names take a trailing underscore (PEP 8).
    Every other name is returned unchanged (``get`` -> ``get``, ``create`` -> ``create``).
    """
    if name in _SHADOWED_NAMES:
        return f"{name}_"
    return name


def resource_client_class(res: ir.Resource) -> str:
    """The resource client class name (``me`` -> ``MeClient``)."""
    return f"{pascal(res.resource)}Client"


def domain_resource_base(res: ir.Resource) -> str:
    """The per-domain resource base class (``tracker`` -> ``TrackerResource``)."""
    return f"{res.domain_title}Resource"


def domain_client_class(res: ir.Resource) -> str:
    """The per-domain transport client class (``tracker`` -> ``TrackerClient``)."""
    return f"{res.domain_title}Client"


def render_doc(text: str | None, indent: str) -> list[str]:
    """Render ``text`` as a triple-quoted docstring block (list of lines) at ``indent``.

    Returns an empty list when ``text`` is absent (so callers can ``+=`` / splat it straight into
    their line buffer). A one-physical-line doc becomes a single triple-quoted line
    (``{indent}\"\"\"{line}\"\"\"``); a multi-line doc opens on the first line
    (``{indent}\"\"\"{line0}``), re-indents every non-blank continuation line to ``indent`` (blank
    lines stay empty), and closes the quotes on their own ``{indent}\"\"\"`` line — the shape ruff
    keeps (it does not re-flow an already-split closing quote).
    """
    if not text:
        return []
    lines = text.split("\n")
    if len(lines) == 1:
        return [f'{indent}"""{text}"""']
    body = [f"{indent}{line}" if line else "" for line in lines[1:]]
    return [f'{indent}"""{lines[0]}', *body, f'{indent}"""']
