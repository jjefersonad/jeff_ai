"""Port do repositório de artefatos SDD (workspace `.specify`)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.sdd import FeatureNumber


class SddArtifactStorePort(ABC):
    """Abstrai o acesso ao workspace de artefatos SDD (leitura de features/estado)."""

    @abstractmethod
    def existing_feature_numbers(self) -> list[FeatureNumber]:
        """Retorna os números de feature já existentes no workspace."""
        raise NotImplementedError
