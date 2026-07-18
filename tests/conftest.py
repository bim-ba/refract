from pathlib import Path

import pytest

from refract import ir
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
