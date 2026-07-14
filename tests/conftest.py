from pathlib import Path

import pytest

from refract import ir
from refract.loader import load

_EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "ycli-tracker"


@pytest.fixture
def me_spec_path() -> Path:
    return _EXAMPLES / "tracker" / "me" / "resource.yaml"


@pytest.fixture
def me_resource(me_spec_path: Path) -> ir.Resource:
    return load(me_spec_path)


@pytest.fixture
def priorities_spec_path() -> Path:
    return _EXAMPLES / "tracker" / "priorities" / "resource.yaml"


@pytest.fixture
def priorities_resource(priorities_spec_path: Path) -> ir.Resource:
    return load(priorities_spec_path)
