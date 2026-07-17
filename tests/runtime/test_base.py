from refract.runtime.base import Resource


def test_resource_stores_session():
    session = object()
    resource = Resource(session)
    assert resource._session is session
