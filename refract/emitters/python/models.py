"""Emit ``models.py`` — the pydantic model set (``APIModel`` subclasses).

For the ``me`` walking skeleton every model is a plain ``object`` model whose fields are optional
scalars (``x: T | None = None``); the ``root_list``/``envelope`` shapes and the ``Field(...)``
wrapper (alias/description) arrive with the first resource that needs them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.python._common import render_doc
from refract.format import ruff_format

if TYPE_CHECKING:
    from refract import ir


def _render_field(field: ir.Field) -> str:
    """One model-field line — ``name: type = default`` (me's fields are optional scalars)."""
    return f"    {field.name}: {field.type} = {field.default}"


def _render_model(model: ir.Model) -> list[str]:
    """The lines for one ``object`` model class (an ``APIModel`` subclass)."""
    lines = [f"class {model.name}(APIModel):"]
    lines += render_doc(model.documentation, "    ")
    lines.append("")
    lines += [_render_field(field) for field in model.fields]
    return lines


def emit(res: ir.Resource) -> str:
    """Render the whole ``models.py`` for ``res`` (ruff-formatted)."""
    out = [
        *render_doc(res.module_docs.models, ""),
        "",
        "from __future__ import annotations",
        "",
        "from ycli.yandex.models import APIModel",
    ]
    for model in res.models:
        out += ["", "", *_render_model(model)]
    rendered = "\n".join(out).rstrip() + "\n"
    return ruff_format(rendered)
