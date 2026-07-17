from refract.emitters.api import Import
from refract.emitters.python import resolve


def test_render_imports_groups_and_merges():
    out = resolve.render_imports(
        (Import(".models", "Me"), Import(".models", "Priority"), Import("typing", "Any"))
    )
    assert "from .models import Me, Priority" in out
    assert "from typing import Any" in out


def test_signature_params_inserts_star_for_keyword_only():
    assert resolve.signature_params(
        ("self", "priority_id: str"), ("version: int | None = None",)
    ) == ("self", "priority_id: str", "*", "version: int | None = None")


def test_signature_params_no_star_when_no_keyword_only():
    assert resolve.signature_params(("self",), ()) == ("self",)


def test_indent_lines_skips_blanks():
    assert resolve.indent_lines(("a", "", "b"), "    ") == ("    a", "", "    b")
