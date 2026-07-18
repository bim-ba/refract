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
