from refract.emitters.api import EmitContext

CTX = EmitContext(package_root="ycli.yandex.tracker")


def _surface():
    from refract.emitters.python.docstrings import PythonDocstrings
    from refract.emitters.python.environment import make_environment
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.cli import CliSurface
    from refract.emitters.python.types import PythonTypeMapper

    return CliSurface(PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment())


def _emit(res):
    from refract.emitters.python.format import RuffFormatter

    return RuffFormatter().format(_surface().emit(res, CTX))


def test_cli_applies_only_when_a_cli_facet_exists(me_resource, priorities_resource):
    assert _surface().applies(me_resource) is True
    assert _surface().applies(priorities_resource) is True  # create/edit now carry a cli facet


def test_me_cli(me_resource):
    out = _emit(me_resource)
    assert '"""`tracker me` commands."""' in out
    assert "from __future__ import annotations" in out
    assert "import typer" in out
    assert "from ycli.cli.context import AppContext" in out
    assert "from ycli.cli.output import Serializer" in out
    assert (
        'app = typer.Typer(name="me", help="Tracker authenticated user.", no_args_is_help=True)'
        in out
    )
    assert "def _group() -> None:" in out
    assert (
        '"""Group anchor - forces subcommand dispatch (no eager DI, so --help stays cred-free)."""'
        in out
    )
    assert "def get(ctx: typer.Context) -> None:" in out
    assert '"""Print the authenticated user (a safe auth probe)."""' in out
    assert "    app_ctx = AppContext.from_typer_context(ctx)" in out
    assert (
        "Serializer.serialize(app_ctx.tracker.me.get(), app_ctx.strategy, app_ctx.console)" in out
    )
