"""Behavioral gate: a bare resource (no models, no mcp/cli/tests facets) must render ONLY the
always-on surfaces. Covers the `applies()` False arm of every facet surface (mcp/cli/tests/models).
"""

from refract import ir
from refract.generation import Generator

_BARE = ir.Resource(
    domain="demo",
    resource="ping",
    security="tok",
    models=(),  # no models
    operations=(
        ir.Operation(
            name="get",
            method="GET",
            path="ping",
            operation_id="ping_get",
            response_model=None,
        ),
    ),  # no mcp/cli/tests facets, bodyless
)
_CONFIG = ir.ClientConfig(
    name="demo",
    server=ir.Server(base_url="https://api.demo/v1"),
    auth=(
        (
            "tok",
            ir.HeaderAuth(
                header="Authorization",
                template="Bearer {t}",
                inputs=(ir.AuthInput(name="t", env="T"),),
            ),
        ),
    ),
)


def test_bare_resource_omits_facet_surfaces():
    files = Generator.for_language("python").render_resource(_BARE, _CONFIG)
    # the always-on surfaces DID render (guards against a vacuous pass if nothing rendered)
    assert any(p.endswith("_requests.py") for p in files)
    assert any(p.endswith("client.py") for p in files)
    assert not any(p.endswith("mcp.py") for p in files)
    assert not any(p.endswith("cli.py") for p in files)
    assert not any(p.endswith("models.py") for p in files)
    assert not any("test_" in p for p in files)
