from pathlib import Path

import pytest

from refract.generation import Generator, _attach_shared
from refract.ir import ObjectModel, Resource
from refract.spec import SpecError, SpecLoader

_EX = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


def _config():
    return SpecLoader.load_client_config(_EX / "client.yaml")


def test_render_resource_gates_surfaces(me_resource, priorities_resource):
    g = Generator.for_language("python")
    config = _config()
    me_files = set(g.render_resource(me_resource, config))
    assert me_files == {
        "tracker/me/__init__.py",
        "tracker/me/models.py",
        "tracker/me/_requests.py",
        "tracker/me/client.py",
        "tracker/me/cli.py",
        "tracker/me/mcp.py",
        "tests/tracker/test_me.py",
    }
    prio_files = set(g.render_resource(priorities_resource, config))
    assert prio_files == {  # create/edit now carry a cli facet -> cli.py included; tests facet
        # present (D1: multi-op client-kind fixtures on list + create) -> tests file included
        "tracker/priorities/__init__.py",
        "tracker/priorities/models.py",
        "tracker/priorities/_requests.py",
        "tracker/priorities/client.py",
        "tracker/priorities/cli.py",
        "tracker/priorities/mcp.py",
        "tests/tracker/test_priorities.py",
    }


def test_render_domain_emits_root_client(me_resource, priorities_resource):
    # domain_surfaces run ONCE over the FULL resource tuple -> the per-API root client
    g = Generator.for_language("python")
    domain_files = g.render_domain((me_resource, priorities_resource), _config())
    assert set(domain_files) == {"tracker/client.py"}
    assert "class TrackerClient" in domain_files["tracker/client.py"]


def test_render_is_ruff_formatted(me_resource):
    out = Generator.for_language("python").render_resource(me_resource, _config())[
        "tracker/me/_requests.py"
    ]
    assert out.endswith("\n") and "def get() -> Request[Me]:" in out


def test_plan_includes_root_client_and_resource_files(tmp_path):
    g = Generator.for_language("python")
    the_plan = g.plan(_EX, tmp_path / "out")
    rels = {p.relative_to(tmp_path / "out").as_posix() for p in the_plan}
    assert "tracker/client.py" in rels  # root client (domain surface, once per domain)
    assert "tracker/me/client.py" in rels  # per-resource
    assert "tracker/me/_requests.py" in rels
    assert "tracker/priorities/_requests.py" in rels


def test_write_then_check_roundtrips(tmp_path):
    g = Generator.for_language("python")
    the_plan = g.plan(_EX, tmp_path / "out")
    assert the_plan
    g.write(the_plan)
    assert g.check(the_plan) == 0


def test_check_detects_drift(tmp_path):
    g = Generator.for_language("python")
    the_plan = g.plan(_EX, tmp_path / "out")
    g.write(the_plan)
    next(iter(the_plan)).write_text("corrupted", encoding="utf-8")
    assert g.check(the_plan) == 1


def test_attach_shared_rejects_name_collision():
    res = Resource(
        domain="k8s",
        resource="pods",
        security="tok",
        models=(ObjectModel(name="ObjectMeta"),),
        operations=(),
    )
    with pytest.raises(SpecError, match=r"defined both locally and in _models\.yaml"):
        _attach_shared(res, (ObjectModel(name="ObjectMeta"),))


def test_plan_threads_shared_models_end_to_end(tmp_path):
    """`_models.yaml` PRESENT, driven through the REAL entry point (`Generator.plan`), not
    `SpecLoader.load_shared_models` called directly.

    `ObjectMeta` is declared ONLY in `_models.yaml` - never in `widgets/resource.yaml`'s own
    `models:`. The `create` op's write body (`WidgetCreate`) carries a `ref<ObjectMeta>` field, so
    the CLI assembler's one-level ref walk (`resolve/cli.py::_assembled_options`) must call
    `res.model("ObjectMeta")`, which only resolves via `res.shared_models` - i.e. only if
    `find_shared_models` located the file AND `Generator.plan` threaded it through
    `SpecLoader.load_shared_models` + `_attach_shared`. If either step is skipped, `res.model(...)`
    raises `KeyError` and `plan()` blows up before this test can even assert.
    """
    (tmp_path / "client.yaml").write_text(
        "name: demo\n"
        "server:\n"
        "  base_url: https://api.example.com\n"
        "default_headers: {}\n"
        "auth:\n"
        "  tok:\n"
        "    kind: header\n"
        "    header: Authorization\n"
        '    template: "Bearer {token}"\n'
        "    inputs:\n"
        "      token: {env: DEMO_TOKEN}\n",
        encoding="utf-8",
    )
    (tmp_path / "_models.yaml").write_text(
        "models:\n"
        "  - name: ObjectMeta\n"
        "    fields:\n"
        "      - {name: name, type: string, optional: true}\n",
        encoding="utf-8",
    )
    resource_dir = tmp_path / "demo" / "widgets"
    resource_dir.mkdir(parents=True)
    (resource_dir / "resource.yaml").write_text(
        "domain: demo\n"
        "resource: widgets\n"
        "security: tok\n"
        "models:\n"
        "  - name: Widget\n"
        "    fields:\n"
        "      - {name: key, type: string, optional: true}\n"
        "  - name: WidgetCreate\n"
        "    fields:\n"
        '      - {name: key, type: string, description: "Key of the new widget."}\n'
        '      - {name: metadata, type: "ref<ObjectMeta>", description: "Shared metadata."}\n'
        "operations:\n"
        "  - name: create\n"
        "    method: POST\n"
        "    path: widgets/\n"
        "    operationId: widgets_create\n"
        "    body: {strategy: TypedModel, model: WidgetCreate, "
        'dump: "by_alias=True, exclude_none=True"}\n'
        "    responses:\n"
        "      200: {model: Widget}\n"
        "    mcp:\n"
        "      name: widgets_create\n"
        "      safety: WRITE\n"
        '      title: "Create widget"\n'
        '      documentation: "Create a widget."\n'
        "    cli:\n"
        "      name: create\n"
        '      documentation: "Create a widget from a key and metadata name."\n',
        encoding="utf-8",
    )

    the_plan = Generator.for_language("python").plan(tmp_path, tmp_path / "out")

    cli_source = the_plan[tmp_path / "out" / "demo" / "widgets" / "cli.py"]
    assert "metadata=ObjectMeta(name=metadata_name)" in cli_source
