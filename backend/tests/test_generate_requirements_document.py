"""Testes do caso de uso GenerateRequirementsDocument (application REQ-001).

Usa um DocumentSinkPort fake — sem filesystem real.
"""
from src.application.ports.document_sink import DocumentSinkPort
from src.application.use_cases import GenerateRequirementsDocument
from src.domain.requirements import DocumentSection


class FakeSink(DocumentSinkPort):
    def __init__(self, sections):
        self._sections = list(sections)
        self.written = None
        self.exclude_seen = "__unset__"

    def collect_sections(self, *, exclude=None):
        self.exclude_seen = exclude
        return list(self._sections)

    def write(self, filename, content):
        self.written = (filename, content)
        return f"/fake/{filename}"


def test_execute_consolidates_and_writes_ordered():
    sink = FakeSink(
        [DocumentSection("02_body.md", "B"), DocumentSection("01_intro.md", "A")]
    )
    result = GenerateRequirementsDocument(sink).execute("final.md")

    assert result.section_count == 2
    assert result.path == "/fake/final.md"
    # exclui o próprio arquivo final ao coletar
    assert sink.exclude_seen == "final.md"
    # gravou o conteúdo consolidado e ORDENADO por nome (intro antes de body)
    filename, content = sink.written
    assert filename == "final.md"
    assert content.index("01_intro.md") < content.index("02_body.md")


def test_execute_without_sections_writes_nothing():
    sink = FakeSink([])
    result = GenerateRequirementsDocument(sink).execute("final.md")

    assert result.section_count == 0
    assert result.path == ""
    assert sink.written is None  # nada é gravado quando não há seções
