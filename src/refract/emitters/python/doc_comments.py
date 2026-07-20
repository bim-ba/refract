from __future__ import annotations

from refract.emitters.ports import DocComments


class PythonDocComments(DocComments):
    """Render a triple-quoted docstring block (tuple of lines) at a given indent."""

    def render(self, text: str | None, indent: str) -> tuple[str, ...]:
        if not text:
            return ()
        lines = text.split("\n")
        if len(lines) == 1:
            return (f'{indent}"""{text}"""',)
        body = tuple(f"{indent}{line}" if line else "" for line in lines[1:])
        return (f'{indent}"""{lines[0]}', *body, f'{indent}"""')
