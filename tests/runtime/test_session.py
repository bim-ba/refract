import httpx
from pydantic import BaseModel

from refract.runtime import Request, Session


class _Me(BaseModel):
    login: str


def _session(handler) -> Session:
    transport = httpx.MockTransport(handler)
    return Session("https://api.example/v3", client=httpx.Client(transport=transport))


def test_send_builds_url_parses_response_model():
    def handler(req):
        assert req.url.path == "/v3/myself"
        return httpx.Response(200, json={"login": "alice"})

    me = _session(handler).send(Request(method="GET", path="myself", response_model=_Me))
    assert isinstance(me, _Me) and me.login == "alice"


def test_send_drops_none_query_and_sends_json():
    def handler(req):
        assert "version" not in req.url.params  # None dropped
        assert req.read() == b'{"name":"x"}'  # httpx encode_json uses compact separators
        return httpx.Response(200, json={"login": "z"})

    _session(handler).send(
        Request(
            method="PATCH",
            path="p/1",
            response_model=_Me,
            query={"version": None},
            json_body={"name": "x"},
        )
    )


def test_send_raises_for_status():
    def handler(req):
        return httpx.Response(404, json={})

    import pytest

    with pytest.raises(httpx.HTTPStatusError):
        _session(handler).send(Request(method="GET", path="missing", response_model=_Me))
