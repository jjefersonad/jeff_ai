"""Ports — interfaces abstratas na fronteira da aplicação.

Aqui vivem as interfaces (ex.: `ImageGenPort`, `StyleRepositoryPort`) que os
casos de uso consomem e que a camada de `infrastructure` implementa. Devem
depender apenas de tipos de `domain`/`application` — nunca de detalhes de
framework.
"""
from src.application.ports.document_sink import DocumentSinkPort
from src.application.ports.document_writer import DocumentWriterPort
from src.application.ports.image_gen import GeneratedImage, ImageGenPort
from src.application.ports.reference_image_fetch import (
    ReferenceImageFetchError,
    ReferenceImageFetchPort,
)
from src.application.ports.sdd_artifact_store import SddArtifactStorePort
from src.application.ports.style_repository import StyleRepositoryPort

__all__ = [
    "DocumentSinkPort",
    "DocumentWriterPort",
    "GeneratedImage",
    "ImageGenPort",
    "ReferenceImageFetchError",
    "ReferenceImageFetchPort",
    "SddArtifactStorePort",
    "StyleRepositoryPort",
]
