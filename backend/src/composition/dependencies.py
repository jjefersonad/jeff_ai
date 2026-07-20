"""Fiação manual (DI) dos casos de uso com adapters concretos de infraestrutura.

Ponto ÚNICO onde a escolha do adapter concreto acontece. Trocar uma implementação
(ex.: outro provedor de imagem, outro sink) muda apenas este módulo — os casos de
uso e o domínio permanecem intactos, pois dependem só dos ports.

Camada de composição (frameworks & drivers): é o único lugar que conhece ao mesmo
tempo os use cases (application) e os adapters concretos (infrastructure).
"""
from __future__ import annotations

import os
from pathlib import Path

from langgraph.config import get_store

from src.application.ports.document_writer import DocumentWriterPort
from src.application.ports.reference_image_fetch import ReferenceImageFetchPort
from src.application.use_cases import (
    CreateDocument,
    GenerateRequirementsDocument,
    GetNextFeatureNumber,
    PlanAndCreateImage,
)
from src.infrastructure.documents import DocxWriter
from src.infrastructure.filesystem.filesystem_document_sink import (
    FilesystemDocumentSink,
)
from src.infrastructure.filesystem.filesystem_sdd_artifact_store import (
    FilesystemSddArtifactStore,
)
from src.infrastructure.llm.gemini_image_adapter import GeminiImageAdapter
from src.infrastructure.persistence.store_style_repository import StoreStyleRepository
from src.infrastructure.web.httpx_reference_image_fetch import HttpxReferenceImageFetch


def build_plan_and_create_image() -> PlanAndCreateImage:
    """Monta PlanAndCreateImage com Gemini + repositório de estilos no Store."""
    return PlanAndCreateImage(
        image_gen=GeminiImageAdapter(),
        styles=StoreStyleRepository(get_store()),
    )


def build_reference_image_fetch() -> ReferenceImageFetchPort:
    """Monta o fetcher de imagem de referência por URL (httpx, com validação/SSRF)."""
    return HttpxReferenceImageFetch()


def build_generate_requirements_document(
    output_dir: str | Path,
) -> GenerateRequirementsDocument:
    """Monta GenerateRequirementsDocument com o sink de filesystem no diretório dado."""
    return GenerateRequirementsDocument(FilesystemDocumentSink(output_dir))


def build_get_next_feature_number(specify_dir: str | Path) -> GetNextFeatureNumber:
    """Monta GetNextFeatureNumber com o store de artefatos SDD no filesystem."""
    return GetNextFeatureNumber(FilesystemSddArtifactStore(specify_dir))


def build_create_document(writer: DocumentWriterPort | None = None) -> CreateDocument:
    """Monta CreateDocument com um writer de documento.

    Sem argumentos, usa o writer nativo de DOCX (python-docx) — preserva o
    contrato legado da tool `create_docx_document`. Tools de outros formatos
    (xlsx/pptx) passam seu próprio writer concreto (XlsxWriter/PptxWriter) por
    injeção. O destino/URL do writer vivem na infraestrutura; este wiring é o
    único ponto que escolhe o adapter concreto. A aplicação permanece agnóstica.

    A `url` retornada precisa ser absoluta para que o agente nunca precise
    inventar um domínio ao apresentá-la (ver `DOCUMENT_BASE_URL` em `.env.example`).
    Sem `DOCUMENT_BASE_URL` explícita, cai para `FRONTEND_ORIGIN` — a mesma env
    var já usada como fonte da verdade para CORS — e só então para o default de
    dev `http://localhost:3000`. `image_server.py:8080` não serve mais estas
    rotas desde `consolidate-http-routes-langgraph`; um default apontando pra lá
    gerava um link morto por padrão (achado em `fix-docx-download-404-file-serving`).
    """
    base_url = (
        os.getenv("DOCUMENT_BASE_URL")
        or os.getenv("FRONTEND_ORIGIN")
        or "http://localhost:3000"
    ).rstrip("/")
    return CreateDocument(writer=writer or DocxWriter(url_prefix=f"{base_url}/api/files"))
