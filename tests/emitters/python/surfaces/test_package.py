from refract.emitters.api import EmitContext
from refract.emitters.python.surfaces.package import PackageSurface

CTX = EmitContext(package_root="ycli.yandex.tracker")


def test_me_package_is_the_resource_docstring(me_resource):
    out = PackageSurface().emit(me_resource, CTX)
    assert out == '"""Tracker /myself resource (the authenticated user)."""\n'


def test_package_always_applies(me_resource):
    assert PackageSurface().applies(me_resource) is True
