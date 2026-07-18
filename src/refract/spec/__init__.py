"""Spec-validation layer: parse+validate resource.yaml / client.yaml -> frozen neutral IR."""

from refract.spec.loader import SpecError, SpecLoader, parse_neutral_type

__all__ = ["SpecError", "SpecLoader", "parse_neutral_type"]
