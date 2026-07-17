from refract import ir
from refract.ir.types import NeutralType


def test_ir_reexports_public_surface():
    for name in (
        "Field",
        "Model",
        "ObjectModel",
        "RootListModel",
        "Param",
        "Operation",
        "Resource",
        "ModuleDocs",
        "Body",
        "McpMeta",
        "CliMeta",
        "TestCase",
        "RequireFound",
        "Safety",
        "TestKind",
        "AuthScheme",
        "AuthInput",
        "HeaderAuth",
        "MultiHeaderAuth",
        "ClientConfig",
        "Server",
    ):
        assert hasattr(ir, name)
    assert ir.NeutralType is NeutralType
