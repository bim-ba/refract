import httpx

from refract.runtime.auth import HeaderAuth, MultiHeaderAuth


def test_header_auth_injects_single_header():
    request = httpx.Request("GET", "https://api.example/v3/myself")
    signed = next(HeaderAuth("Authorization", "Bearer t").auth_flow(request))
    assert signed.headers["Authorization"] == "Bearer t"


def test_multi_header_auth_injects_both_headers():
    request = httpx.Request("GET", "https://api.example/v3/myself")
    auth = MultiHeaderAuth({"Authorization": "OAuth tok", "X-Org-Id": "42"})
    signed = next(auth.auth_flow(request))
    assert signed.headers["Authorization"] == "OAuth tok"
    assert signed.headers["X-Org-Id"] == "42"
