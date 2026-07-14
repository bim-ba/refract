from pathlib import Path

import pytest

from refract import cli
from refract.generate import check, plan, render_resource, write

_EX = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"
_GOLDEN = _EX / "golden"


def test_render_resource_is_byte_identical_to_golden(me_resource):
    files = render_resource(me_resource)
    assert set(files) == {
        "tracker/me/__init__.py",
        "tracker/me/models.py",
        "tracker/me/client.py",
        "tracker/me/cli.py",
        "tracker/me/mcp.py",
        "tests/tracker/test_me.py",
    }
    for rel, content in files.items():
        assert content == (_GOLDEN / rel).read_text("utf-8"), rel


def test_check_passes_on_committed_tree():
    the_plan = plan(_EX, _EX / "out")
    assert the_plan  # non-empty: at least the me resource rendered
    assert check(the_plan) == 0


def test_check_detects_drift(tmp_path):
    stale_out = tmp_path / "out"
    fresh_plan = plan(_EX, stale_out)
    write(fresh_plan)

    corrupted = stale_out / "tracker" / "me" / "models.py"
    corrupted.write_text("corrupted", encoding="utf-8")

    assert check(fresh_plan) == 1


def test_check_reports_missing_file_as_drift(tmp_path):
    # a plan whose files were never written to disk is stale too (not just corrupted content).
    fresh_plan = plan(_EX, tmp_path / "out")
    assert check(fresh_plan) == 1


def test_cli_no_flag_prints_plan_without_touching_disk(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_OUT_DIR", tmp_path / "out")
    assert cli.main(["generate"]) == 0
    assert "would render" in capsys.readouterr().out
    assert not (tmp_path / "out").exists()


def test_cli_write_then_check_round_trips(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_OUT_DIR", tmp_path / "out")
    assert cli.main(["generate", "--write"]) == 0
    assert (tmp_path / "out" / "tracker" / "me" / "models.py").exists()
    assert cli.main(["generate", "--check"]) == 0


def test_cli_check_detects_drift(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "_OUT_DIR", tmp_path / "out")
    assert cli.main(["generate", "--write"]) == 0
    (tmp_path / "out" / "tracker" / "me" / "models.py").write_text("corrupted", encoding="utf-8")
    assert cli.main(["generate", "--check"]) == 1


def test_cli_spec_error_exits_2(monkeypatch, tmp_path):
    bad_specs = tmp_path / "specs" / "tracker" / "me"
    bad_specs.mkdir(parents=True)
    (bad_specs / "resource.yaml").write_text("domain: tracker\nunknown_key: 1\n", encoding="utf-8")

    monkeypatch.setattr(cli, "_SPECS_DIR", bad_specs.parent.parent)
    monkeypatch.setattr(cli, "_OUT_DIR", tmp_path / "out")

    assert cli.main(["generate", "--write"]) == 2


def test_cli_requires_a_subcommand():
    with pytest.raises(SystemExit):
        cli.main([])
