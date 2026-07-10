"""Testes do domínio de leitura de documentos (`document_content`, `read_limits`).

Cobrem os critérios de aceitação da task `document-reading-tools-task-scaffold-1`:
- `DocumentContent` e blocos por formato, com metadados exclusivos da leitura.
- `ReadLimits` como política de truncamento no domínio, e `ReadBudget` aplicando-a.
- `DocumentContent` NÃO reusa nem estende `DocumentSpec`.
- O domínio não importa framework, lib de parsing nem I/O.
"""
from __future__ import annotations

import pytest

from src.domain.documents import (
    DocumentContent,
    DocumentResult,
    DocxSpec,
    HeadingBlock,
    PageContent,
    ParagraphBlock,
    PptxSpec,
    ReadBudget,
    ReadLimits,
    ReadMetadata,
    SheetContent,
    SlideContent,
    TableBlock,
    XlsxSpec,
)
from src.domain.shared.errors import DomainError


class TestReadLimits:
    """A política de truncamento vive no domínio, não nos adapters."""

    def test_rejeita_teto_nao_positivo(self) -> None:
        for kwargs in ({"max_chars": 0}, {"max_cells": -1}, {"max_units": 0}):
            with pytest.raises(DomainError):
                ReadLimits(**kwargs)

    def test_rejeita_bool_como_teto(self) -> None:
        # `True` é `int` em Python; um teto booleano é sempre erro de programação.
        with pytest.raises(DomainError):
            ReadLimits(max_chars=True)

    def test_tetos_padrao_sao_positivos(self) -> None:
        limits = ReadLimits()
        assert limits.max_chars > 0
        assert limits.max_cells > 0
        assert limits.max_units > 0


class TestReadBudget:
    """O orçamento para de acumular ao atingir o teto, em vez de truncar no fim."""

    def test_texto_dentro_do_teto_passa_intacto(self) -> None:
        budget = ReadBudget(ReadLimits(max_chars=10))
        assert budget.take_text("abc") == "abc"
        assert budget.truncated is False

    def test_texto_acima_do_teto_e_truncado_e_sinalizado(self) -> None:
        budget = ReadBudget(ReadLimits(max_chars=5))
        assert budget.take_text("abcdefgh") == "abcde"
        assert budget.truncated is True

    def test_orcamento_esgotado_devolve_vazio(self) -> None:
        budget = ReadBudget(ReadLimits(max_chars=3))
        budget.take_text("abc")
        assert budget.take_text("mais texto") == ""
        assert budget.truncated is True

    def test_consumo_de_texto_e_acumulativo(self) -> None:
        budget = ReadBudget(ReadLimits(max_chars=6))
        assert budget.take_text("abc") == "abc"
        assert budget.take_text("defgh") == "def"
        assert budget.truncated is True

    def test_celulas_e_unidades_respeitam_seus_tetos(self) -> None:
        budget = ReadBudget(ReadLimits(max_cells=2, max_units=1))
        assert budget.take_cell() is True
        assert budget.take_cell() is True
        assert budget.take_cell() is False
        assert budget.take_unit() is True
        assert budget.take_unit() is False
        assert budget.truncated is True


class TestBlocosPermissivos:
    """A leitura aceita o que a escrita recusa — arquivos reais são imperfeitos."""

    def test_paragrafo_lido_aceita_texto_vazio(self) -> None:
        # `Paragraph` (escrita) levanta DomainError aqui; `ParagraphBlock` não.
        assert ParagraphBlock("").text == ""

    def test_tabela_lida_aceita_linhas_de_larguras_diferentes(self) -> None:
        # Células mescladas produzem linhas irregulares; `Table` (escrita) recusaria.
        block = TableBlock(rows=(("a", "b"), ("c",)))
        assert block.rows == (("a", "b"), ("c",))

    def test_tabela_lida_normaliza_celulas_para_str(self) -> None:
        assert TableBlock(rows=((1, 2.5),)).rows == (("1", "2.5"),)

    def test_heading_lido_valida_o_nivel(self) -> None:
        assert HeadingBlock("Título", level=1).level == 1
        with pytest.raises(DomainError):
            HeadingBlock("Título", level=0)
        with pytest.raises(DomainError):
            HeadingBlock("Título", level=10)

    def test_slide_sem_notas_usa_string_vazia(self) -> None:
        slide = SlideContent(index=0, title=None, texts=("corpo",))
        assert slide.notes == ""

    def test_pagina_de_pdf_aceita_texto_vazio_mas_exige_numero_valido(self) -> None:
        assert PageContent(number=1, text="").text == ""
        with pytest.raises(DomainError):
            PageContent(number=0, text="x")

    def test_aba_exige_nome_e_total_de_linhas_coerente(self) -> None:
        sheet = SheetContent(name="Plan1", rows=(("a",),), total_rows=9999)
        assert sheet.total_rows == 9999
        with pytest.raises(DomainError):
            SheetContent(name="", rows=(), total_rows=0)
        with pytest.raises(DomainError):
            SheetContent(name="Plan1", rows=(), total_rows=-1)


class TestReadMetadata:
    """Metadados carregam o que só a leitura sabe: truncamento e totais reais."""

    def test_rejeita_kind_desconhecido(self) -> None:
        with pytest.raises(DomainError):
            ReadMetadata(kind="doc")

    def test_omite_campos_que_nao_se_aplicam_ao_formato(self) -> None:
        data = ReadMetadata(kind="docx", total_paragraphs=3).to_dict()
        assert data == {"kind": "docx", "truncated": False, "total_paragraphs": 3}
        assert "page_count" not in data
        assert "has_text_layer" not in data

    def test_pdf_escaneado_sinaliza_ausencia_de_camada_de_texto(self) -> None:
        # `has_text_layer=False` precisa sobreviver à serialização: é o que impede
        # o agente de concluir que um PDF escaneado está em branco.
        data = ReadMetadata(kind="pdf", page_count=2, has_text_layer=False).to_dict()
        assert data["has_text_layer"] is False
        assert data["page_count"] == 2

    def test_planilha_sinaliza_formula_sem_valor_em_cache(self) -> None:
        data = ReadMetadata(kind="xlsx", has_uncomputed_formulas=True).to_dict()
        assert data["has_uncomputed_formulas"] is True

    def test_totais_negativos_sao_rejeitados(self) -> None:
        with pytest.raises(DomainError):
            ReadMetadata(kind="pptx", total_slides=-1)


class TestDocumentContent:
    """O agregado da leitura, e sua separação deliberada do agregado de escrita."""

    def test_constroi_conteudo_de_docx(self) -> None:
        content = DocumentContent(
            kind="docx",
            blocks=(HeadingBlock("Intro", level=1), ParagraphBlock("texto")),
            metadata=ReadMetadata(kind="docx", total_paragraphs=1),
        )
        assert content.kind == "docx"
        assert len(content.blocks) == 2

    def test_rejeita_kind_desconhecido(self) -> None:
        with pytest.raises(DomainError):
            DocumentContent(kind="txt", blocks=(), metadata=ReadMetadata(kind="docx"))

    def test_rejeita_metadata_de_outro_formato(self) -> None:
        with pytest.raises(DomainError):
            DocumentContent(kind="docx", blocks=(), metadata=ReadMetadata(kind="pdf"))

    def test_nao_reusa_nem_estende_document_spec(self) -> None:
        # Decisão de design: um round-trip ler→escrever perderia formatação em
        # silêncio, o que é pior que a ausência dele.
        for spec_type in (DocxSpec, XlsxSpec, PptxSpec):
            assert not issubclass(DocumentContent, spec_type)
            assert not issubclass(spec_type, DocumentContent)

    def test_contrato_de_retorno_nao_tem_path_nem_url(self) -> None:
        # `DocumentResult` (escrita) expõe path/url; a leitura não produz artefato.
        assert DocumentContent.RESULT_KEYS == ("content", "metadata")
        assert "path" not in DocumentContent.RESULT_KEYS
        assert "url" not in DocumentContent.RESULT_KEYS
        assert {"path", "url"} <= set(DocumentResult.__dataclass_fields__)


def test_dominio_de_leitura_nao_importa_frameworks_nem_libs_de_parsing() -> None:
    """O domínio é puro: nenhum import de lib de parsing, framework ou I/O.

    `make arch` (import-linter) já enforça a Regra da Dependência para o pacote
    inteiro; este teste trava especificamente os módulos novos, para que a
    violação apareça no `pytest` e não só no gate de arquitetura.
    """
    import ast
    from pathlib import Path

    import src.domain.documents.document_content as content_module
    import src.domain.documents.read_limits as limits_module

    proibidos = {
        "docx",
        "openpyxl",
        "pptx",
        "pypdf",
        "fastapi",
        "langchain",
        "langgraph",
        "deepagents",
        "os",
        "pathlib",
    }

    for module in (content_module, limits_module):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        raizes: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                raizes.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                raizes.add(node.module.split(".")[0])

        assert not (raizes & proibidos), f"{module.__name__} importa {raizes & proibidos}"
