from refract.runtime.base import Resource


def test_resource_stores_session():
    session = object()
    resource = Resource(session)  # ty: ignore[invalid-argument-type]  # opaque storage: any object
    assert resource._session is session
