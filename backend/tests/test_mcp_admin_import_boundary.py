"""Teste de arquitetura: nenhum módulo do universo do agente importa
`mcp_admin_api`/`mcp_config_store` (task `retire-image-server-task-core-2`).

Substitui o isolamento físico de processo (removido em `retire-image-server`)
como garantia de custom-http-app REQ-004 / mcp-client REQ-001: um scan
estático (`ast`) de `src/tools/`, `src/agents/` (exceto os dois arquivos
admin) e `src/composition/` falha se qualquer arquivo importar os módulos
que compõem a API administrativa de MCP.
"""
from __future__ import annotations

import ast
from pathlib import Path

_BACKEND_SRC = Path(__file__).resolve().parent.parent / "src"

_SCANNED_DIRS = [
    _BACKEND_SRC / "tools",
    _BACKEND_SRC / "agents",
    _BACKEND_SRC / "composition",
]

_EXCLUDED_FILES = {
    _BACKEND_SRC / "agents" / "unified" / "mcp_admin_api.py",
    _BACKEND_SRC / "agents" / "unified" / "mcp_config_store.py",
}

_FORBIDDEN_MODULES = {"mcp_admin_api", "mcp_config_store"}


def _imported_module_names(node: ast.AST) -> set[str]:
    if isinstance(node, ast.Import):
        return {alias.name.rsplit(".", 1)[-1] for alias in node.names}
    if isinstance(node, ast.ImportFrom) and node.module:
        return {node.module.rsplit(".", 1)[-1]}
    return set()


def find_forbidden_imports(
    scanned_dirs: list[Path], excluded_files: set[Path], forbidden_modules: set[str]
) -> dict[Path, set[str]]:
    violations: dict[Path, set[str]] = {}
    for directory in scanned_dirs:
        for path in sorted(directory.rglob("*.py")):
            if path in excluded_files:
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            hit = {
                name
                for node in ast.walk(tree)
                for name in _imported_module_names(node) & forbidden_modules
            }
            if hit:
                violations[path] = hit
    return violations


def test_no_agent_module_imports_mcp_admin_modules() -> None:
    violations = find_forbidden_imports(_SCANNED_DIRS, _EXCLUDED_FILES, _FORBIDDEN_MODULES)

    assert not violations, (
        "Módulos do universo do agente não podem importar mcp_admin_api/"
        f"mcp_config_store (viola mcp-client REQ-001): {violations}"
    )


def test_scanner_detects_synthetic_violation(tmp_path: Path) -> None:
    fixture_dir = tmp_path / "tools"
    fixture_dir.mkdir()
    fixture_file = fixture_dir / "bad_tool.py"
    fixture_file.write_text("from src.agents.unified.mcp_config_store import add_server\n")

    violations = find_forbidden_imports([fixture_dir], set(), _FORBIDDEN_MODULES)

    assert fixture_file in violations
    assert violations[fixture_file] == {"mcp_config_store"}
