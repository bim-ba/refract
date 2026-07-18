from __future__ import annotations

from jinja2 import Environment, PackageLoader, StrictUndefined


def make_environment() -> Environment:
    """The single Jinja Environment for the Python backend (see Global Constraints)."""
    return Environment(
        loader=PackageLoader("refract.emitters.python", "templates"),
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        undefined=StrictUndefined,
    )
