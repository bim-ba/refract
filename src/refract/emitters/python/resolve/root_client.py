from __future__ import annotations

from typing import TYPE_CHECKING, assert_never

from refract.emitters.ports import Import
from refract.emitters.python.resolve._common import (
    indent_lines,
    render_imports,
    signature_params,
)
from refract.emitters.python.views import RootClientPageView
from refract.ir import HeaderAuth, MultiHeaderAuth
from refract.spec import SpecError

# NB: `MultiHeaderAuth`/`HeaderAuth` here are the ir.auth DESCRIPTORS (AuthScheme variants) used
# for the `match` below; the generated code imports the same-named httpx mechanisms from
# `.runtime.auth` - the resolver only ever emits the mechanism's string name.

if TYPE_CHECKING:
    from refract import ir
    from refract.emitters.ports import DocComments, EmitContext, Naming


def _auth_value(template: str, inputs: tuple[ir.AuthInput, ...]) -> str:
    """One header value: a bare input var for a pure ``"{name}"`` placeholder, else an f-string.

    ``"{organization_id}"`` -> ``organization_id``; ``"OAuth {oauth_token}"`` ->
    ``f"OAuth {oauth_token}"``.
    """
    for auth_input in inputs:
        if template == f"{{{auth_input.name}}}":
            return auth_input.name
    return f'f"{template}"'


def _multi_header_call(scheme: MultiHeaderAuth) -> str:
    """``MultiHeaderAuth({...})`` mechanism call from the scheme's ``(header, template)`` pairs."""
    entries = ", ".join(
        f'"{header}": {_auth_value(template, scheme.inputs)}' for header, template in scheme.headers
    )
    return f"MultiHeaderAuth({{{entries}}})"


def _header_call(scheme: HeaderAuth) -> str:
    """``HeaderAuth("<header>", <value>)`` mechanism call (single templated header)."""
    return f'HeaderAuth("{scheme.header}", {_auth_value(scheme.template, scheme.inputs)})'


def _select_scheme(config: ir.ClientConfig, security: str) -> ir.AuthScheme:
    """Index ``ClientConfig.auth`` (tuple-of-pairs) by the resource's ``security`` scheme name."""
    for name, scheme in config.auth:
        if name == security:
            return scheme
    raise SpecError(f"security {security!r} names no auth scheme in client.yaml")


def resolve_root_client(
    resources: tuple[ir.Resource, ...],
    ctx: EmitContext,
    naming: Naming,
    doc_comments: DocComments,
) -> RootClientPageView:
    """IR + ClientConfig -> RootClientPageView: the composition root. Runs once over ALL
    resources (per-API invariant: shared ``domain`` + ``security``, so read from ``resources[0]``).
    """
    if ctx.config is None:
        raise ValueError("root_client surface requires ClientConfig (server + auth)")
    domain = resources[0].domain
    client_class = naming.class_name(domain, "Client")
    scheme = _select_scheme(ctx.config, resources[0].security)
    match scheme:
        case MultiHeaderAuth():
            mechanism, auth_expr = "MultiHeaderAuth", _multi_header_call(scheme)
        case HeaderAuth():
            mechanism, auth_expr = "HeaderAuth", _header_call(scheme)
        case _:
            assert_never(scheme)

    ctor_params = signature_params(
        ("self",), tuple(f"{auth_input.name}: str" for auth_input in scheme.inputs)
    )
    init_lines = (
        f"def __init__({', '.join(ctor_params)}) -> None:",
        f"    auth = {auth_expr}",
        f'    session = Session("{ctx.config.server.base_url}", client=httpx.Client(auth=auth))',
        *(
            f"    self.{res.resource} = {naming.class_name(res.resource, 'Client')}(session)"
            for res in resources
        ),
    )
    from_env_lines = (
        "@classmethod",
        f"def from_env(cls) -> {client_class}:",
        *doc_comments.render(
            "The single sanctioned env-read point (composition root); components never read env.",
            "    ",
        ),
        "    return cls(",
        *(
            f'        {auth_input.name}=os.environ["{auth_input.env}"],'
            for auth_input in scheme.inputs
        ),
        "    )",
    )
    imports = (
        "import os",
        "import httpx",
        *render_imports(
            (
                Import(".runtime.session", "Session"),
                Import(".runtime.auth", mechanism),
                *(
                    Import(f".{res.resource}.client", naming.class_name(res.resource, "Client"))
                    for res in resources
                ),
            )
        ),
    )
    title = resources[0].domain_title
    return RootClientPageView(
        doc_block=doc_comments.render(
            f"{title} client - the composition root (aggregates resources, owns transport + auth).",
            "",
        ),
        header_lines=("from __future__ import annotations",),
        import_lines=imports,
        class_header=f"class {client_class}:",
        class_doc_lines=doc_comments.render(f"Root client for the {title} API.", "    "),
        methods=(
            "\n".join(indent_lines(init_lines, "    ")),
            "\n".join(indent_lines(from_env_lines, "    ")),
        ),
    )
