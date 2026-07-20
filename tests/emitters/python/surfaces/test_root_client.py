from refract import ir
from refract.emitters.ports import EmitContext

# Root-client glue is resolved from ClientConfig: server + the auth scheme a resource's
# `security` names. The scheme's AuthInput.name values drive the ctor params + from_env, and the
# (header, template) pairs render the MultiHeaderAuth mechanism dict.
CTX = EmitContext(
    package_root="ycli.yandex.tracker",
    config=ir.ClientConfig(
        name="tracker",
        server=ir.Server(base_url="https://api.tracker.yandex.net/v3"),
        auth=(
            (
                "oauth_token",
                ir.MultiHeaderAuth(
                    headers=(
                        ("Authorization", "OAuth {oauth_token}"),
                        ("X-Org-Id", "{organization_id}"),
                    ),
                    inputs=(
                        ir.AuthInput(name="oauth_token", env="YANDEX_ID_OAUTH_TOKEN"),
                        ir.AuthInput(name="organization_id", env="YANDEX_ID_ORGANIZATION_ID"),
                    ),
                ),
            ),
        ),
    ),
)


def _emit(resources):
    from refract.emitters.python.doc_comments import PythonDocComments
    from refract.emitters.python.format import RuffFormatter
    from refract.emitters.python.naming import PythonNaming
    from refract.emitters.python.surfaces.root_client import RootClientSurface
    from refract.emitters.python.templating import make_template_environment
    from refract.emitters.python.types import PythonTypeMapper

    surface = RootClientSurface(
        PythonNaming(), PythonTypeMapper(), PythonDocComments(), make_template_environment()
    )
    return RuffFormatter().format(surface.emit(resources, CTX))


def test_tracker_root_client(me_resource, priorities_resource):
    out = _emit((me_resource, priorities_resource))
    # module + class framing (title synthesised from domain_title - see docstring note above)
    assert (
        '"""Tracker client - the composition root '
        '(aggregates resources, owns transport + auth)."""' in out
    )
    assert "from __future__ import annotations" in out
    assert "class TrackerClient:" in out
    assert '"""Root client for the Tracker API."""' in out
    # imports (ruff isort-sorted): stdlib os, third-party httpx, local relative
    assert "import os" in out
    assert "import httpx" in out
    assert "from .me.client import MeClient" in out
    assert "from .priorities.client import PrioritiesClient" in out
    assert "from .runtime.auth import MultiHeaderAuth" in out
    assert "from .runtime.session import Session" in out
    # constructor: keyword-only credential params from AuthScheme.inputs (AuthInput.name)
    assert "def __init__(self, *, oauth_token: str, organization_id: str) -> None:" in out
    # auth mechanism from (header, template) pairs - pure `{placeholder}` -> bare var, decorated
    # template -> f-string (ruff hug-wraps the >100-col MultiHeaderAuth(...) call, so assert frags)
    assert "auth = MultiHeaderAuth(" in out
    assert '"Authorization": f"OAuth {oauth_token}"' in out
    assert '"X-Org-Id": organization_id' in out
    # session from ctx.config.server.base_url
    assert (
        'session = Session("https://api.tracker.yandex.net/v3", '
        "client=httpx.Client(auth=auth))" in out
    )
    # resource aggregation over the passed resources tuple (order preserved)
    assert "self.me = MeClient(session)" in out
    assert "self.priorities = PrioritiesClient(session)" in out
    # from_env: single sanctioned env-read point, one kwarg per AuthInput.env
    assert "def from_env(cls) -> TrackerClient:" in out
    assert (
        '"""The single sanctioned env-read point (composition root); '
        'components never read env."""' in out
    )
    assert 'oauth_token=os.environ["YANDEX_ID_OAUTH_TOKEN"]' in out
    assert 'organization_id=os.environ["YANDEX_ID_ORGANIZATION_ID"]' in out
