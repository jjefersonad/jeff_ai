"""Casos de uso — uma operação de negócio por caso de uso.

Cada caso de uso recebe ports por injeção e orquestra o domínio, com entrada e
saída explícitas. Deve ser testável com dublês (fakes) dos ports, sem Postgres,
LLM real ou filesystem.
"""
from src.application.use_cases.generate_requirements_document import (
    ConsolidationResult,
    GenerateRequirementsDocument,
)
from src.application.use_cases.get_next_feature_number import GetNextFeatureNumber
from src.application.use_cases.plan_and_create_image import PlanAndCreateImage

__all__ = [
    "ConsolidationResult",
    "GenerateRequirementsDocument",
    "GetNextFeatureNumber",
    "PlanAndCreateImage",
]
