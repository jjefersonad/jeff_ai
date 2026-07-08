"""Domínio de requirements — documento de requisitos (entidades, VOs, service) puro."""
from src.domain.requirements.document_section import DocumentSection
from src.domain.requirements.merge import consolidate
from src.domain.requirements.requirement_document import RequirementDocument

__all__ = ["DocumentSection", "RequirementDocument", "consolidate"]
