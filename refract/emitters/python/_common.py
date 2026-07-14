"""Shared naming + formatting helpers for the Python emitters (no IR-shape logic here)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from refract import ir


def pascal(name: str) -> str:
    """``snake_case`` -> ``PascalCase`` (``comments`` -> ``Comments``, ``me`` -> ``Me``)."""
    return "".join(part.capitalize() for part in name.split("_"))


def resource_client_class(res: ir.Resource) -> str:
    """The resource client class name (``me`` -> ``MeClient``)."""
    return f"{pascal(res.resource)}Client"


def domain_resource_base(res: ir.Resource) -> str:
    """The per-domain resource base class (``tracker`` -> ``TrackerResource``)."""
    return f"{res.domain_title}Resource"


def render_doc(text: str | None, indent: str) -> list[str]:
    """Render ``text`` as a one-line triple-quoted docstring block at ``indent`` (``[]`` if absent).

    Returns a single-element list so callers can ``+=`` / splat it straight into their line
    buffer, or an empty list when ``text`` is absent. Multi-line docstring shaping arrives with
    the first resource whose docs span several lines.
    """
    return [f'{indent}"""{text}"""'] if text else []
