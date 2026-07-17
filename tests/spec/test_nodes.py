import pytest
from pydantic import ValidationError

from refract.spec.nodes import ClientConfigNode, ResourceSpec


def test_unknown_key_rejected():
    with pytest.raises(ValidationError):
        ResourceSpec.model_validate(
            {"domain": "t", "resource": "m", "security": "s", "operations": [], "bogus": 1}
        )


def test_base_url_now_rejected():  # base_url переехал в client.yaml (разд. J)
    with pytest.raises(ValidationError):
        ResourceSpec.model_validate(
            {"domain": "t", "resource": "m", "security": "s", "base_url": "u", "operations": []}
        )


def test_operation_id_aliased_from_camel():
    spec = ResourceSpec.model_validate(
        {
            "domain": "t",
            "resource": "m",
            "security": "s",
            "operations": [
                {
                    "name": "get",
                    "method": "GET",
                    "path": "myself",
                    "operationId": "me_get",
                    "responses": {200: {"model": "Me"}},
                    "mcp": {"name": "me_get", "safety": "RO", "title": "x", "documentation": "y"},
                }
            ],
        }
    )
    assert spec.operations[0].operation_id == "me_get"


def test_field_type_stays_raw_string():
    spec = ResourceSpec.model_validate(
        {
            "domain": "t",
            "resource": "m",
            "security": "s",
            "models": [{"name": "Me", "fields": [{"name": "uid", "type": "integer"}]}],
            "operations": [],
        }
    )
    assert spec.models[0].fields[0].type == "integer"  # NOT lowered here


def test_client_config_node_parses_multi_header_auth():
    node = ClientConfigNode.model_validate(
        {
            "name": "tracker",
            "server": {"base_url": "https://api.tracker.yandex.net/v3"},
            "default_headers": {},
            "auth": {
                "oauth_token": {
                    "kind": "multi_header",
                    "headers": {
                        "Authorization": "OAuth {oauth_token}",
                        "X-Org-Id": "{organization_id}",
                    },
                    "inputs": {
                        "oauth_token": {"env": "YANDEX_ID_OAUTH_TOKEN"},
                        "organization_id": {"env": "YANDEX_ID_ORGANIZATION_ID"},
                    },
                }
            },
        }
    )
    assert node.server.base_url.endswith("/v3")
    scheme = node.auth["oauth_token"]
    assert scheme.kind == "multi_header"  # discriminated on `kind`
    assert scheme.headers["Authorization"] == "OAuth {oauth_token}"  # still a MAPPING here
    assert scheme.inputs["oauth_token"].env == "YANDEX_ID_OAUTH_TOKEN"


def test_client_config_rejects_unknown_auth_kind():
    with pytest.raises(ValidationError):
        ClientConfigNode.model_validate(
            {"name": "x", "server": {"base_url": "u"}, "auth": {"s": {"kind": "bogus"}}}
        )
