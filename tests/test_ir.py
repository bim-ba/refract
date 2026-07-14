from refract import ir


def test_resource_is_hashable_and_accessor_works():
    me = ir.Model(name="Me", fields=(ir.Field(name="login", type="str | None", default="None"),))
    res = ir.Resource(
        domain="tracker",
        resource="me",
        base_url="https://api.tracker.yandex.net/v3",
        security="oauth_token",
        models=(me,),
        operations=(),
    )
    assert hash(res) == hash(res)  # frozen + tuples => hashable
    assert res.model("Me") is me
    assert res.domain_title == "Tracker"


def test_unknown_model_raises_keyerror():
    res = ir.Resource(
        domain="tracker",
        resource="me",
        base_url="x",
        security="oauth_token",
        models=(),
        operations=(),
    )
    import pytest

    with pytest.raises(KeyError):
        res.model("Nope")
