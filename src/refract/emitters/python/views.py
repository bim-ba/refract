from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _View(BaseModel):
    """Base for every view-model: frozen, and every field a resolved primitive.

    No ir/shape tags leak into the fields.
    """

    model_config = ConfigDict(frozen=True)


class RequestsPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    functions: tuple[str, ...] = ()


class ClientPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    class_header: str
    class_doc_lines: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()


class ModelsPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()


class CliPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    blocks: tuple[str, ...] = ()


class McpPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    server_line: str = ""
    tools: tuple[str, ...] = ()


class TestsPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    constants: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()


class RootClientPageView(_View):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    class_header: str
    class_doc_lines: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
