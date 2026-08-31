from __future__ import annotations

from refract.emitters.ports import LanguageBackend
from refract.emitters.python.doc_comments import PythonDocComments
from refract.emitters.python.file_layout import PythonFileLayout
from refract.emitters.python.format import RuffFormatter
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.surfaces import python_domain_surfaces, python_surfaces
from refract.emitters.python.templating import make_template_environment
from refract.emitters.python.types import PythonTypeMapper
from refract.emitters.registry import backend


@backend("python")
def python_backend() -> LanguageBackend:
    """Compose the Python backend: 5 injected strategies + 7 per-resource surfaces + root_client/
    shared_models domain glue."""
    env = make_template_environment()
    return LanguageBackend(
        name="python",
        naming=PythonNaming(),
        type_mapper=PythonTypeMapper(),
        formatter=RuffFormatter(),
        doc_comments=PythonDocComments(),
        file_layout=PythonFileLayout(),
        surfaces=python_surfaces(env),
        domain_surfaces=python_domain_surfaces(env),
    )
