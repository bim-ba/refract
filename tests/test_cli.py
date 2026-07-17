from pathlib import Path

from typer.testing import CliRunner

from refract.cli import app

runner = CliRunner()
_EX = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


def test_no_flag_prints_plan_without_writing(tmp_path):
    out = tmp_path / "out"
    res = runner.invoke(app, ["generate", "--specs", str(_EX), "--out", str(out)])
    assert res.exit_code == 0 and "would render" in res.stdout
    assert not out.exists()


def test_write_then_check_roundtrips(tmp_path):
    out = tmp_path / "out"
    write_res = runner.invoke(
        app, ["generate", "--specs", str(_EX), "--out", str(out), "--write"]
    )
    assert write_res.exit_code == 0
    assert (out / "tracker" / "me" / "_requests.py").exists()
    assert (out / "tracker" / "client.py").exists()   # root-client glue written too
    check_res = runner.invoke(
        app, ["generate", "--specs", str(_EX), "--out", str(out), "--check"]
    )
    assert check_res.exit_code == 0


def test_spec_error_exits_2(tmp_path):
    root = tmp_path / "specs"
    bad = root / "tracker" / "me"
    bad.mkdir(parents=True)
    (bad / "resource.yaml").write_text("domain: t\nunknown_key: 1\n", encoding="utf-8")
    (root / "client.yaml").write_text(
        "name: t\nserver:\n  base_url: https://x/v1\nauth: {}\n", encoding="utf-8")
    res = runner.invoke(app, ["generate", "--specs", str(root), "--out", str(tmp_path / "out")])
    assert res.exit_code == 2


def test_missing_client_yaml_exits_2(tmp_path):
    bad = tmp_path / "specs" / "tracker" / "me"
    bad.mkdir(parents=True)
    (bad / "resource.yaml").write_text("domain: t\nsecurity: token\n", encoding="utf-8")
    res = runner.invoke(
        app, ["generate", "--specs", str(tmp_path / "specs"), "--out", str(tmp_path / "out")]
    )
    assert res.exit_code == 2  # find_client_config raises SpecError -> exit 2


def test_requires_subcommand():
    assert runner.invoke(app, []).exit_code != 0
