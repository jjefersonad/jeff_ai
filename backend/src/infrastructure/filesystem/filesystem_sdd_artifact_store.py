"""Adapter de filesystem do workspace SDD (`SddArtifactStorePort`)."""
from __future__ import annotations

from pathlib import Path

from src.application.ports.sdd_artifact_store import SddArtifactStorePort
from src.domain.sdd import FeatureNumber


class FilesystemSddArtifactStore(SddArtifactStorePort):
    """Lê o workspace `.specify` no filesystem para obter os números de feature."""

    def __init__(self, specify_dir: str | Path) -> None:
        """Vincula o store ao diretório `.specify` (que contém `specs/`)."""
        self._specs_dir = Path(specify_dir).resolve() / "specs"

    def existing_feature_numbers(self) -> list[FeatureNumber]:
        """Escaneia `specs/` e retorna os números das features existentes (prefixo NNN)."""
        self._specs_dir.mkdir(parents=True, exist_ok=True)
        numbers: list[FeatureNumber] = []
        for entry in self._specs_dir.iterdir():
            if entry.is_dir() and entry.name[:3].isdigit():
                numbers.append(FeatureNumber(int(entry.name[:3])))
        return numbers
