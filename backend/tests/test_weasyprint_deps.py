"""Deps WeasyPrint para HTML→PDF (html-document-tools-task-deps-1)."""
from __future__ import annotations

from pathlib import Path

import tomllib

_BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Pacotes de sistema mínimos exigidos pelo WeasyPrint no Debian/Ubuntu.
_WEASYPRINT_APT_PACKAGES = (
    "libpango-1.0-0",
    "libpangocairo-1.0-0",
    "libgdk-pixbuf-2.0-0",
    "libcairo2",
    "fonts-dejavu-core",
)


def test_pyproject_declares_weasyprint() -> None:
    """Unit: pyproject.toml lista a dependência WeasyPrint."""
    pyproject = _BACKEND_ROOT / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    deps = data["project"]["dependencies"]
    assert any(
        dep.lower().startswith("weasyprint") for dep in deps
    ), deps


def test_dockerfile_declares_weasyprint_system_and_python_deps() -> None:
    """Unit: Dockerfile.backend instala libs de sistema + pin WeasyPrint."""
    dockerfile = _BACKEND_ROOT / "Dockerfile.backend"
    text = dockerfile.read_text(encoding="utf-8")
    for pkg in _WEASYPRINT_APT_PACKAGES:
        assert pkg in text, f"missing apt package {pkg!r} in Dockerfile.backend"
    pins = [
        line.strip().strip("\\").strip().strip('"').strip("'")
        for line in text.splitlines()
        if "weasyprint==" in line.lower()
    ]
    assert pins, "Dockerfile.backend must pin weasyprint==… in RUN pip install"
    assert any(pin.lower().startswith("weasyprint==") for pin in pins), pins
