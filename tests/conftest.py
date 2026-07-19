from pathlib import Path

import pytest

from refract import ir
from refract.emitters.api import LanguageBackend
from refract.emitters.python.backend import python_backend as _make_python_backend
from refract.spec import SpecLoader

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


@pytest.fixture
def me_spec_path() -> Path:
    return _EXAMPLES / "tracker" / "me" / "resource.yaml"


@pytest.fixture
def me_resource(me_spec_path: Path) -> ir.Resource:
    return SpecLoader.load(me_spec_path)


@pytest.fixture
def priorities_spec_path() -> Path:
    return _EXAMPLES / "tracker" / "priorities" / "resource.yaml"


@pytest.fixture
def priorities_resource(priorities_spec_path: Path) -> ir.Resource:
    return SpecLoader.load(priorities_spec_path)


@pytest.fixture
def client_config_path() -> Path:
    return _EXAMPLES / "client.yaml"


@pytest.fixture
def client_config(client_config_path: Path) -> ir.ClientConfig:
    return SpecLoader.load_client_config(client_config_path)


@pytest.fixture
def python_backend() -> LanguageBackend:
    return _make_python_backend()


@pytest.fixture
def two_resources_sharing_objectmeta() -> tuple[ir.Resource, ir.Resource]:
    """Two same-domain resources with IDENTICAL ``shared_models=(ObjectMeta,)`` (Task 9's
    ``_attach_shared`` invariant: attached once per domain, byte-identical across resources),
    each embedding a ``ref<ObjectMeta>`` field on its own local model - the anchor for
    `SharedModelsSurface`'s emit-once behavior + `resolve_models`'s shared-import scan."""
    meta = ir.ObjectModel(
        name="ObjectMeta",
        fields=(ir.Field(name="name", type=ir.ScalarType(scalar="string"), optional=True),),
    )
    pod = ir.ObjectModel(
        name="Pod", fields=(ir.Field(name="metadata", type=ir.RefType(target="ObjectMeta")),)
    )
    service = ir.ObjectModel(
        name="Service", fields=(ir.Field(name="metadata", type=ir.RefType(target="ObjectMeta")),)
    )
    pods = ir.Resource(
        domain="k8s",
        resource="pods",
        security="oauth_token",
        models=(pod,),
        operations=(),
        shared_models=(meta,),
    )
    services = ir.Resource(
        domain="k8s",
        resource="services",
        security="oauth_token",
        models=(service,),
        operations=(),
        shared_models=(meta,),
    )
    return pods, services
