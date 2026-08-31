from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PageView(BaseModel):
    """Base for every view-model: frozen, and every field a resolved primitive.

    No ir/shape tags leak into the fields.
    """

    model_config = ConfigDict(frozen=True)


class RequestsPageView(PageView):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    functions: tuple[str, ...] = ()


class ClientPageView(PageView):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    class_header: str
    class_doc_lines: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()


class ModelsPageView(PageView):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    classes: tuple[str, ...] = ()


class CliPageView(PageView):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    blocks: tuple[str, ...] = ()


class McpPageView(PageView):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    server_line: str = ""
    tools: tuple[str, ...] = ()


class TestsPageView(PageView):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    constants: tuple[str, ...] = ()
    tests: tuple[str, ...] = ()


class RootClientPageView(PageView):
    doc_block: tuple[str, ...] = ()
    header_lines: tuple[str, ...] = ()
    import_lines: tuple[str, ...] = ()
    class_header: str
    class_doc_lines: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
