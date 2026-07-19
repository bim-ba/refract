from refract.generation import Generator


def test_shared_models_emitted_once_across_two_resources(
    python_backend, two_resources_sharing_objectmeta, client_config
):
    """Two k8s resources (pods, services) each embed `ref<ObjectMeta>` and carry the SAME
    `shared_models=(ObjectMeta,)` (Task 9's `_attach_shared` invariant). `SharedModelsSurface`
    is a DomainEmitter (runs ONCE over the domain), so `ObjectMeta` lands in `k8s/shared_models.py`
    exactly once - never re-defined inside either resource's own `models.py`."""
    pods, services = two_resources_sharing_objectmeta
    generator = Generator(python_backend)
    files: dict[str, str] = {}
    for res in (pods, services):
        files |= generator.render_resource(res, client_config)
    files |= generator.render_domain((pods, services), client_config)

    shared_files = [path for path in files if path == "k8s/shared_models.py"]
    assert len(shared_files) == 1  # ObjectMeta emitted ONCE
    assert "class ObjectMeta" in files[shared_files[0]]
    for path in ("k8s/pods/models.py", "k8s/services/models.py"):
        assert "class ObjectMeta" not in files[path]  # never re-defined per-resource
        assert "from ycli.yandex.k8s.shared_models import ObjectMeta" in files[path]


def test_shared_models_surface_omitted_when_no_shared_models(
    python_backend, priorities_resource, client_config
):
    files = Generator(python_backend).render_domain((priorities_resource,), client_config)
    assert not any(path.endswith("shared_models.py") for path in files)  # applies() False arm


def test_resource_referencing_shared_model_imports_from_shared_module():
    """A resource whose field type is `ref<ObjectMeta>` (ObjectMeta shared, NOT local): its
    models.py imports ObjectMeta from `<package_root>.shared_models`, not from `.models`."""
    from refract.emitters.api import EmitContext
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.resolve import resolve_models
    from refract.emitters.python.types import PythonTypeMapper
    from refract.ir import Field, ObjectModel, Resource
    from refract.ir.types import RefType

    meta = ObjectModel(name="ObjectMeta")
    pod = ObjectModel(
        name="Pod", fields=(Field(name="metadata", type=RefType(target="ObjectMeta")),)
    )
    res = Resource(
        domain="k8s",
        resource="pods",
        security="tok",
        models=(pod,),
        operations=(),
        shared_models=(meta,),
    )
    ctx = EmitContext(package_root="ycli.yandex.k8s")
    page = resolve_models(res, ctx, PythonNaming(), PythonTypeMapper(), PythonDocstrings())
    assert "from ycli.yandex.k8s.shared_models import ObjectMeta" in page.import_lines


def test_resource_referencing_shared_model_in_container_imports_from_shared_module():
    """C1 regression: a shared ref WRAPPED in a list/map/union (not a direct field) must STILL be
    imported from the shared module. `items: list<ref<ObjectMeta>>` renders `list[ObjectMeta]`;
    the one-level `isinstance(field.type, RefType)` scan missed it, so the generated models.py named
    ObjectMeta with no import -> not importable (PydanticUndefinedAnnotation). The k8s `PodList`
    shape is exactly Task 10's motivating case."""
    from refract.emitters.api import EmitContext
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.resolve import resolve_models
    from refract.emitters.python.types import PythonTypeMapper
    from refract.ir import Field, ObjectModel, Resource
    from refract.ir.types import ListType, RefType

    meta = ObjectModel(name="ObjectMeta")
    pod_list = ObjectModel(
        name="PodList",
        fields=(Field(name="items", type=ListType(item=RefType(target="ObjectMeta"))),),
    )
    res = Resource(
        domain="k8s",
        resource="pods",
        security="tok",
        models=(pod_list,),
        operations=(),
        shared_models=(meta,),
    )
    ctx = EmitContext(package_root="ycli.yandex.k8s")
    page = resolve_models(res, ctx, PythonNaming(), PythonTypeMapper(), PythonDocstrings())
    assert "from ycli.yandex.k8s.shared_models import ObjectMeta" in page.import_lines


def test_type_ref_targets_unwraps_containers_without_recursing_into_models():
    """`_type_ref_targets` names a type's OWN top-level ref targets, unwrapping list/map/union at
    any depth, but never recurses into a referenced model - that keeps `_shared_ref_imports` from
    over-importing a shared model's own internal refs into a consuming resource's models.py."""
    from refract.emitters.python.resolve._common import _type_ref_targets
    from refract.ir.types import ListType, LiteralType, MapType, RefType, ScalarType, UnionType

    assert _type_ref_targets(RefType(target="A")) == ("A",)
    assert _type_ref_targets(ListType(item=RefType(target="A"))) == ("A",)
    assert _type_ref_targets(
        MapType(key=ScalarType(scalar="string"), value=RefType(target="V"))
    ) == ("V",)
    assert _type_ref_targets(UnionType(variants=(RefType(target="A"), RefType(target="B")))) == (
        "A",
        "B",
    )
    assert _type_ref_targets(ScalarType(scalar="string")) == ()
    assert _type_ref_targets(LiteralType(value="x")) == ()


def test_body_test_imports_routes_shared_transitive_ref_to_shared_module():
    """C2 (case-3): a CLIENT test's authored `call` constructs a body model whose field reaches a
    SHARED model (`WidgetCreate{metadata: ref<ObjectMeta>}`). The transitive import for that shared
    name must resolve to the per-domain shared module, not the resource-local models module (which
    would dangle at import/run time)."""
    from refract.emitters.python.resolve.tests import _body_test_imports
    from refract.ir import Body, Field, ObjectModel, Resource
    from refract.ir.types import RefType

    meta = ObjectModel(name="ObjectMeta")
    create = ObjectModel(
        name="WidgetCreate", fields=(Field(name="metadata", type=RefType(target="ObjectMeta")),)
    )
    res = Resource(
        domain="demo",
        resource="widgets",
        security="tok",
        models=(create,),
        operations=(),
        shared_models=(meta,),
    )
    imports = _body_test_imports(
        res,
        Body(model="WidgetCreate"),
        "ycli.yandex.demo.widgets.models",
        "ycli.yandex.demo.shared_models",
    )
    modules = {(imp.module, imp.name) for imp in imports}
    assert ("ycli.yandex.demo.shared_models", "ObjectMeta") in modules
    assert ("ycli.yandex.demo.widgets.models", "WidgetCreate") in modules
    assert ("ycli.yandex.demo.widgets.models", "ObjectMeta") not in modules
