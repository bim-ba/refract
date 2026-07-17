from pathlib import Path

import pytest

from refract import ir
from refract.ir.model import ObjectModel, RootListModel
from refract.ir.types import RefType, ScalarType
from refract.spec.loader import SpecError, SpecLoader

_EX = Path(__file__).resolve().parent.parent.parent / "examples" / "ycli-tracker"


def test_loads_me_as_neutral_ir():
    res = SpecLoader.load(_EX / "tracker" / "me" / "resource.yaml")
    assert res.domain == "tracker" and res.resource == "me"
    assert not hasattr(res, "base_url")  # base_url moved to client.yaml
    uid = res.model("Me").fields[0]
    assert uid.name == "uid"
    assert uid.type == ScalarType(scalar="integer")  # neutral, NOT "int | None"
    assert uid.optional is True
    assert uid.default is None  # implied null-default is the TypeMapper's job now


def test_me_model_is_object_variant():
    res = SpecLoader.load(_EX / "tracker" / "me" / "resource.yaml")
    assert isinstance(res.model("Me"), ObjectModel)


def test_priorities_model_variants_and_ref_field():
    res = SpecLoader.load(_EX / "tracker" / "priorities" / "resource.yaml")
    assert isinstance(res.model("PriorityList"), RootListModel)
    assert res.model("PriorityList").item == "Priority"
    assert isinstance(res.model("Priority"), ObjectModel)
    name = res.model("PriorityCreate").fields[1]
    assert name.type == RefType(target="LocalizedName")


def test_create_body_flags_default_true():
    res = SpecLoader.load(_EX / "tracker" / "priorities" / "resource.yaml")
    create = next(op for op in res.operations if op.name == "create")
    assert create.body is not None
    assert create.body.model == "PriorityCreate"
    assert create.body.by_alias is True and create.body.omit_none is True  # no `dump` text


def test_query_param_is_neutral():
    res = SpecLoader.load(_EX / "tracker" / "priorities" / "resource.yaml")
    edit = next(op for op in res.operations if op.name == "edit")
    version = next(p for p in edit.params if p.name == "version")
    assert version.type == ScalarType(scalar="integer") and version.optional is True


def test_loads_tracker_client_config():
    config = SpecLoader.load_client_config(_EX / "client.yaml")
    assert config.name == "tracker"
    assert config.server.base_url == "https://api.tracker.yandex.net/v3"
    assert len(config.auth) == 1
    name, scheme = config.auth[0]
    assert name == "oauth_token"
    assert isinstance(scheme, ir.MultiHeaderAuth)
    assert scheme.headers == (
        ("Authorization", "OAuth {oauth_token}"),
        ("X-Org-Id", "{organization_id}"),
    )
    assert tuple((i.name, i.env) for i in scheme.inputs) == (
        ("oauth_token", "YANDEX_ID_OAUTH_TOKEN"),
        ("organization_id", "YANDEX_ID_ORGANIZATION_ID"),
    )


def test_root_list_without_item_raises_spec_error(tmp_path: Path):
    resource_yaml = tmp_path / "resource.yaml"
    resource_yaml.write_text(
        """
domain: t
resource: m
security: s
operations: []
models:
  - name: X
    kind: root_list
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="root_list requires 'item'"):
        SpecLoader.load(resource_yaml)
