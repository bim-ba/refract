"""L3 proof for Task 6 (default B): the loader synthesizes each discriminated-union variant's
`Literal[tag]` field with NO hand-authoring, and pydantic actually discriminates on it.

A tiny Notion-style block union (Paragraph / Heading1Block, discriminated by `type`) goes through
the REAL entry point (`SpecLoader.load` from a YAML file, not `_resource` directly), then the
real `ModelsSurface` + `RuffFormatter` render an importable models module. Nobody in the spec
below writes a `type` field - `_synthesize_discriminators` injects it.
"""

import importlib
import sys

import pytest
from pydantic import ValidationError

from refract.emitters.api import EmitContext
from refract.emitters.python.docstrings import PythonDocstrings
from refract.emitters.python.environment import make_environment
from refract.emitters.python.format import RuffFormatter
from refract.emitters.python.naming import PythonNaming
from refract.emitters.python.surfaces.models import ModelsSurface
from refract.emitters.python.types import PythonTypeMapper
from refract.spec.loader import SpecLoader

pytestmark = pytest.mark.behavioral

_RESOURCE_YAML = """
domain: notion
resource: blocks
security: tok
models:
  - name: Paragraph
    fields:
      - {name: text, type: string, optional: true}
  - name: Heading1Block
    fields:
      - {name: text, type: string, optional: true}
  - name: Block
    fields:
      - name: block
        oneof:
          discriminator: type
          variants:
            paragraph: "ref<Paragraph>"
            heading_1: "ref<Heading1Block>"
operations:
  - name: get
    method: GET
    path: blocks
    operationId: blocks_get
    responses:
      200: {model: Block}
    mcp:
      name: blocks_get
      safety: RO
      title: Get
      documentation: Get a block.
"""


def _write_models_module(tmp_path):
    """Generate `blockpkg/notion/models.py` from the spec above + an APIModel shim it imports."""
    resource_yaml = tmp_path / "resource.yaml"
    resource_yaml.write_text(_RESOURCE_YAML, encoding="utf-8")
    res = SpecLoader.load(resource_yaml)

    parts = (PythonNaming(), PythonTypeMapper(), PythonDocstrings(), make_environment())
    ctx = EmitContext(package_root="blockpkg.notion")
    source = RuffFormatter().format(ModelsSurface(*parts).emit(res, ctx))

    pkg = tmp_path / "blockpkg"
    (pkg / "notion").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    # APIModel shim: models.jinja always imports it from one level above package_root (D2/G2
    # convention) - a bare pydantic BaseModel subclass is all the discriminated-union proof needs.
    (pkg / "models.py").write_text(
        "from pydantic import BaseModel\n\n\nclass APIModel(BaseModel):\n    pass\n",
        encoding="utf-8",
    )
    (pkg / "notion" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "notion" / "models.py").write_text(source, encoding="utf-8")
    return source


def test_generated_block_union_discriminates_on_synthesized_tag(tmp_path, monkeypatch):
    """Default B end to end: the spec above never spells a `type` field on either variant, yet
    the generated source carries the synthesized `Literal[...]` tag AND pydantic uses it to
    discriminate real JSON (unknown tag -> ValidationError)."""
    source = _write_models_module(tmp_path)
    assert 'type: Literal["heading_1"]' in source  # synthesized, never spelled in the YAML above
    assert 'type: Literal["paragraph"]' in source
    assert "Field(discriminator=" in source  # Block.block is the Annotated discriminated union

    monkeypatch.syspath_prepend(str(tmp_path))
    try:
        models = importlib.import_module("blockpkg.notion.models")
        block = models.Block.model_validate({"block": {"type": "heading_1", "text": "hi"}})
        assert isinstance(block.block, models.Heading1Block)
        assert block.block.text == "hi"

        with pytest.raises(ValidationError):
            models.Block.model_validate({"block": {"type": "unknown_tag", "text": "hi"}})
    finally:
        for name in ("blockpkg.notion.models", "blockpkg.notion", "blockpkg.models", "blockpkg"):
            sys.modules.pop(name, None)
