from pathlib import Path

from refract.generation import Generator
from refract.spec import SpecLoader

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
