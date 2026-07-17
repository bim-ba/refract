"""Emit ``models.py`` — the pydantic model set (``APIModel`` subclasses).

Two model kinds are rendered today: an ``object`` model whose fields are ``x: T | None = None`` or
``x: T = Field(...)`` (``me``'s scalars + ``priorities``' typed write bodies), and a ``root_list``
model — a ``RootModel[list[Item]]`` public list with just a docstring. The ``envelope`` shape
arrives with the first resource whose listing paginates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.python._common import render_doc
from refract.format import ruff_format

if TYPE_CHECKING:
    from refract import ir


def _render_field(field: ir.Field) -> str:
    """One model-field line — a plain ``name: type = default`` or a ``Field(...)`` when described.

    A described field renders ``Field(...)``: an optional one carries ``default=<default>`` before
    ``description=``, a required one carries only ``description=`` (no default). Long calls are left
    on one line for the ruff post-pass to wrap.
    """
    if not field.description:
        return f"    {field.name}: {field.type} = {field.default}"
    arguments = []
    if field.default is not None:
        arguments.append(f"default={field.default}")
    arguments.append(f'description="{field.description}"')
    return f"    {field.name}: {field.type} = Field({', '.join(arguments)})"


def _render_model(model: ir.Model) -> list[str]:
    """The lines for one model class — an ``object`` ``APIModel`` or a ``root_list``."""
    if model.kind == "root_list":
        lines = [f"class {model.name}(RootModel[list[{model.item}]]):"]
        return lines + render_doc(model.documentation, "    ")
    lines = [f"class {model.name}(APIModel):"]
    lines += render_doc(model.documentation, "    ")
    lines.append("")
    lines += [_render_field(field) for field in model.fields]
    return lines


def _pydantic_imports(res: ir.Resource) -> list[str]:
    """The ``pydantic`` names this module needs — ``Field`` for described fields, ``RootModel`` for
    a ``root_list`` model (``[]`` when neither, e.g. ``me``)."""
    names = []
    if any(field.description for model in res.models for field in model.fields):
        names.append("Field")
    if any(model.kind == "root_list" for model in res.models):
        names.append("RootModel")
    return names


def emit(res: ir.Resource) -> str:
    """Render the whole ``models.py`` for ``res`` (ruff-formatted)."""
    out = [
        *render_doc(res.module_docs.models, ""),
        "",
        "from __future__ import annotations",
    ]
    pydantic_names = _pydantic_imports(res)
    if pydantic_names:
        out += ["", f"from pydantic import {', '.join(pydantic_names)}"]
    out += ["", "from ycli.yandex.models import APIModel"]
    for model in res.models:
        out += ["", "", *_render_model(model)]
    rendered = "\n".join(out).rstrip() + "\n"
    return ruff_format(rendered)
