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
    me = res.model("Me")
    assert isinstance(me, ObjectModel)  # narrow the model union before field access
    uid = me.fields[0]
    assert uid.name == "uid"
    assert uid.type == ScalarType(scalar="integer")  # neutral, NOT "int | None"
    assert uid.optional is True
    assert uid.default is None  # implied null-default is the TypeMapper's job now


def test_me_model_is_object_variant():
    res = SpecLoader.load(_EX / "tracker" / "me" / "resource.yaml")
    assert isinstance(res.model("Me"), ObjectModel)


def test_priorities_model_variants_and_ref_field():
    res = SpecLoader.load(_EX / "tracker" / "priorities" / "resource.yaml")
    plist = res.model("PriorityList")
    assert isinstance(plist, RootListModel)
    assert plist.item == "Priority"
    assert isinstance(res.model("Priority"), ObjectModel)
    create = res.model("PriorityCreate")
    assert isinstance(create, ObjectModel)
    name = create.fields[1]
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


def test_load_missing_file_raises_spec_error():
    with pytest.raises(SpecError):
        SpecLoader.load(Path("/nonexistent/resource.yaml"))


def test_load_client_config_with_single_header_auth(tmp_path: Path):
    client_yaml = tmp_path / "client.yaml"
    client_yaml.write_text(
        """
name: widgets
server:
  base_url: https://api.widgets.example/v1
auth:
  bearer_token:
    kind: header
    header: Authorization
    template: "Bearer {token}"
    inputs:
      token: {env: WIDGETS_TOKEN}
""",
        encoding="utf-8",
    )
    config = SpecLoader.load_client_config(client_yaml)
    name, scheme = config.auth[0]
    assert name == "bearer_token"
    assert isinstance(scheme, ir.HeaderAuth)
    assert scheme.header == "Authorization"
    assert scheme.template == "Bearer {token}"
    assert tuple((i.name, i.env) for i in scheme.inputs) == (("token", "WIDGETS_TOKEN"),)


def test_load_non_mapping_top_level_raises_spec_error(tmp_path: Path):
    resource_yaml = tmp_path / "resource.yaml"
    resource_yaml.write_text("- not\n- a\n- mapping\n", encoding="utf-8")
    with pytest.raises(SpecError, match="top level must be a mapping"):
        SpecLoader.load(resource_yaml)


def test_load_client_config_validation_error_raises_spec_error(tmp_path: Path):
    client_yaml = tmp_path / "client.yaml"
    client_yaml.write_text(
        """
name: widgets
server:
  base_url: https://api.widgets.example/v1
auth:
  bearer_token:
    kind: header
    header: Authorization
    # missing required 'template' and 'inputs' keys -> pydantic ValidationError
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="client config failed validation"):
        SpecLoader.load_client_config(client_yaml)


def test_operation_without_200_response_raises_spec_error(tmp_path: Path):
    resource_yaml = tmp_path / "resource.yaml"
    resource_yaml.write_text(
        """
domain: t
resource: m
security: s
operations:
  - name: get
    method: GET
    path: p
    operationId: get
    responses:
      404: {model: Error}
    mcp:
      name: get
      safety: RO
      title: t
      documentation: d
""",
        encoding="utf-8",
    )
    with pytest.raises(SpecError, match="'get' has no 200 response"):
        SpecLoader.load(resource_yaml)


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
