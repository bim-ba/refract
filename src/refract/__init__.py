"""refract — a language-agnostic, spec-driven multi-surface code generator."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("refract")
except PackageNotFoundError:  # not installed (raw checkout on sys.path)
    __version__ = "0.0.0+unknown"
