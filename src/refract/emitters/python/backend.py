from __future__ import annotations

from refract.emitters.api import LanguageBackend
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.environment import make_environment
from refract.emitters.python.format import RuffFormatter
from refract.emitters.python.layout import PythonLayout
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.surfaces.cli import CliSurface
from refract.emitters.python.surfaces.client import ClientSurface
from refract.emitters.python.surfaces.mcp import McpSurface
from refract.emitters.python.surfaces.models import ModelsSurface
from refract.emitters.python.surfaces.package import PackageSurface
from refract.emitters.python.surfaces.requests import RequestsSurface
from refract.emitters.python.surfaces.root_client import RootClientSurface
from refract.emitters.python.surfaces.tests import TestsSurface
from refract.emitters.python.types import PythonTypeMapper
from refract.emitters.registry import backend


@backend("python")
def python_backend() -> LanguageBackend:
    """Compose the Python backend: 5 injected strategies + 7 per-resource surfaces + root_client
    glue."""
    naming = PythonNaming()
    type_mapper = PythonTypeMapper()
    docstrings = PythonDocstrings()
    env = make_environment()
    parts = (naming, type_mapper, docstrings, env)
    surfaces = (
        PackageSurface(),
        ModelsSurface(*parts),
        RequestsSurface(*parts),
        ClientSurface(*parts),
        CliSurface(*parts),
        McpSurface(*parts),
        TestsSurface(*parts),
    )
    return LanguageBackend(
        name="python",
        naming=naming,
        type_mapper=type_mapper,
        formatter=RuffFormatter(),
        docstrings=docstrings,
        layout=PythonLayout(),
        surfaces=surfaces,
        domain_surfaces=(RootClientSurface(*parts),),
    )
