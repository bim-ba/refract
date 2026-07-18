from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from refract.emitters.api import Import
from refract.emitters.python.resolve._common import (
    _shared_models_module,
    py_str,
    render_imports,
)
from refract.emitters.python.views import ModelsPageView
from refract.ir import ObjectModel, RootListModel

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.api import Docstrings, EmitContext, Naming, TypeMapper


def _model_field(field: ir.Field, type_mapper: TypeMapper) -> tuple[str, list[Import]]:
    """One model field line: ``name: Type = default``, ``name: Type = Field(...)`` for a
    described/aliased field, or ``name: Annotated[Type, Field(discriminator=...)]`` for a
    discriminated union - the ONE place that assembles ``Field(...)``, so a discriminated field
    with a description merges into a SINGLE ``Field(...)`` call rather than nesting two.

    The type renders from NeutralType via TypeMapper (the key port shift); the default is the
    explicit ``field.default`` or, absent that, ``type_mapper.null_default(...)`` (implied-null).
    A discriminated union has NO trailing ``= default`` - pydantic requires its ``Field(...)``
    to live inside ``Annotated[...]``, ordered ``discriminator`` first, then ``alias``, then
    ``description``. Long calls stay one line - ruff wraps them.
    """
    rendered = type_mapper.render(field.type, optional=field.optional)
    imports = list(rendered.imports)
    default = (
        field.default
        if field.default is not None
        else type_mapper.null_default(field.type, optional=field.optional)
    )
    # A format-coerced field always carries an explicit `None` default (regardless of
    # `field.optional`): its Python type is only as trustworthy as the wire coercion behind it,
    # so - absent an explicit `field.default` - it renders defensively rather than as required.
    if rendered.coercer is not None and default is None:
        default = "None"
    text = rendered.text
    # `coercer` and `discriminator` never co-occur on one field (`format` is scalar-only; a union
    # is not a scalar) - these two wrap branches are INDEPENDENT and compose, neither nested
    # inside the other.
    if rendered.coercer is not None:
        # `render`'s optional wrap appends this exact " | None" suffix OUTSIDE the base text; strip
        # it before the Annotated wrap and re-append it after, so `| None` stays the outermost
        # union member: `Annotated[int, BeforeValidator(coerce_int64)] | None`, not
        # `Annotated[int | None, BeforeValidator(coerce_int64)]`.
        optional_suffix = " | None" if text.endswith(" | None") else ""
        base_text = text.removesuffix(" | None")
        text = f"Annotated[{base_text}, BeforeValidator({rendered.coercer})]{optional_suffix}"
        imports += [Import("typing", "Annotated"), Import("pydantic", "BeforeValidator")]
    if rendered.discriminator is not None:
        text = f"Annotated[{text}, __FIELD__]"
        imports += [Import("typing", "Annotated"), Import("pydantic", "Field")]
    if rendered.discriminator is None and not field.description and not field.alias:
        # A required field (no explicit default, non-optional) has `default is None` here - emit a
        # bare `name: type` (pydantic-required), NOT `name: type = None` which would default it to
        # None and mistype a non-None annotation. An optional field's `default` is the STRING
        # "None" (from null_default), so it still renders `= None`.
        if default is None:
            return f"    {field.name}: {text}", imports
        return f"    {field.name}: {text} = {default}", imports
    arguments: list[str] = []
    if rendered.discriminator is not None:
        arguments.append(f"discriminator={py_str(rendered.discriminator)}")
    if default is not None and rendered.discriminator is None:
        arguments.append(f"default={default}")
    if field.alias is not None:
        arguments.append(f"alias={py_str(field.alias)}")
    if field.description is not None:
        arguments.append(f"description={py_str(field.description)}")
    field_call = f"Field({', '.join(arguments)})"
    if rendered.discriminator is not None:  # Field lives INSIDE Annotated[...], never as default
        return f"    {field.name}: {text.replace('__FIELD__', field_call)}", imports
    return f"    {field.name}: {text} = {field_call}", imports


def _model_class(
    model: ir.Model, type_mapper: TypeMapper, docstrings: Docstrings
) -> tuple[str, list[Import]]:
    """The finished source for one model class - dispatches over the ``Model`` union.

    ``RootListModel`` -> ``RootModel[list[Item]]`` with just a docstring; ``ObjectModel`` ->
    docstring, blank line, then fields. ``model.item`` is the model name (a str, not a
    NeutralType) and renders verbatim. ``assert_never`` keeps the union exhaustive - a new
    variant is a type error, not a silent no-op.
    """
    match model:
        case RootListModel():
            lines = [
                f"class {model.name}(RootModel[list[{model.item}]]):",
                *docstrings.render(model.documentation, "    "),
            ]
            return "\n".join(lines), []
        case ObjectModel():
            lines = [f"class {model.name}(APIModel):"]
            lines += docstrings.render(model.documentation, "    ")
            lines.append("")
            imports: list[Import] = []
            for field in model.fields:
                decl, field_imports = _model_field(field, type_mapper)
                lines.append(decl)
                imports += field_imports
            return "\n".join(lines), imports
        case _:
            assert_never(model)


def resolve_models(
    res: ir.Resource,
    ctx: EmitContext,
    naming: Naming,
    type_mapper: TypeMapper,
    docstrings: Docstrings,
) -> ModelsPageView:
    """IR -> ModelsPageView: module docstring, imports (APIModel + pydantic + those collected
    from types), finished classes. ``APIModel`` is always imported."""
    imports: list[Import] = [Import(_shared_models_module(ctx), "APIModel")]
    if any(
        field.description or field.alias
        for model in res.models
        if isinstance(model, ObjectModel)
        for field in model.fields
    ):
        imports.append(Import("pydantic", "Field"))
    if any(isinstance(model, RootListModel) for model in res.models):
        imports.append(Import("pydantic", "RootModel"))
    for model in res.models:
        if not isinstance(model, ObjectModel):
            continue
        for field in model.fields:
            rendered = type_mapper.render(field.type, optional=field.optional)
            if rendered.coercer is not None:
                # The coercer helper (e.g. `coerce_int64`) is HAND-WRITTEN in the shared base
                # module alongside `APIModel`/`require_found` - refract emits only the wiring.
                imports.append(Import(_shared_models_module(ctx), rendered.coercer))
    classes: list[str] = []
    for model in res.models:
        text, class_imports = _model_class(model, type_mapper, docstrings)
        classes.append(text)
        imports += class_imports
    return ModelsPageView(
        doc_block=docstrings.render(res.module_docs.models, ""),
        header_lines=("from __future__ import annotations",),
        import_lines=render_imports(tuple(imports)),
        classes=tuple(classes),
    )
