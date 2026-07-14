"""Emit ``client.py`` — the declarative uplink transport client (HTTP lives ONLY here).

Reproduces the ycli client idioms for the ``me`` walking skeleton: no ``from __future__ import
annotations`` (uplink reads annotations eagerly), the ``@uplink.returns.json()`` /
``@uplink.<verb>(path)`` decorator stack, and the ``# ty: ignore[empty-body]`` empty-body method.
The offset-drain / bodyless-write / typed-body method shapes arrive with the resources that need
them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from refract.emitters.python._common import (
    domain_resource_base,
    render_doc,
    resource_client_class,
)
from refract.format import ruff_format

if TYPE_CHECKING:
    from refract import ir


def _model_imports(res: ir.Resource) -> str:
    """The ``from ...models import <Model>`` line for the models the client methods return."""
    module = f"ycli.yandex.{res.domain}.{res.resource}.models"
    names = sorted({op.response_model for op in res.operations if op.response_model})
    return f"from {module} import {', '.join(names)}"


def _decorators(operation: ir.Operation) -> list[str]:
    """The ``@uplink.*`` decorator stack for one JSON read endpoint."""
    return [
        "    @uplink.returns.json()",
        f'    @uplink.{operation.method.lower()}("{operation.path}")',
    ]


def _method(operation: ir.Operation) -> list[str]:
    """A single uplink-decorated (empty-body) endpoint method."""
    lines = _decorators(operation)
    lines.append(
        f"    def {operation.name}(self) -> {operation.response_model}:  # ty: ignore[empty-body]"
    )
    lines += render_doc(operation.documentation, "        ")
    return lines


def emit(res: ir.Resource) -> str:
    """Render the whole ``client.py`` for ``res`` (ruff-formatted)."""
    out = [
        *render_doc(res.module_docs.client, ""),
        "",
        "import uplink",
        "",
        f"from ycli.yandex.{res.domain}.base import {domain_resource_base(res)}",
        _model_imports(res),
        "",
        "",
        f"class {resource_client_class(res)}({domain_resource_base(res)}):",
        *render_doc(res.module_docs.client_class, "    "),
    ]
    for operation in res.operations:
        out.append("")
        out += _method(operation)
    rendered = "\n".join(out).rstrip() + "\n"
    return ruff_format(rendered)
