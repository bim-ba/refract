from refract import ir
from refract.emitters.python.backend import python_backend
from refract.emitters.python.surfaces import PackageSurface

_CONFIG = ir.ClientConfig(name="tracker", server=ir.Server(base_url="https://api.example"))

CTX = python_backend().context("ycli.yandex.tracker", _CONFIG)


def test_me_package_is_the_resource_docstring(me_resource):
    out = PackageSurface().emit(me_resource, CTX)
    assert out == '"""Tracker /myself resource (the authenticated user)."""\n'


def test_package_always_applies(me_resource):
    assert PackageSurface().applies(me_resource) is True
