"""Caso de uso: determinar o próximo número de feature SDD."""
from __future__ import annotations

from src.application.ports.sdd_artifact_store import SddArtifactStorePort
from src.domain.sdd import FeatureNumber


class GetNextFeatureNumber:
    """Retorna o próximo `FeatureNumber` a partir dos já existentes no workspace."""

    def __init__(self, store: SddArtifactStorePort) -> None:
        """Recebe a implementação do port por injeção de dependência."""
        self._store = store

    def execute(self) -> FeatureNumber:
        """Calcula o próximo número (regra de sequência no domínio)."""
        return FeatureNumber.next_after(self._store.existing_feature_numbers())
