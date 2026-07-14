"""Ferramenta de execução de testes para o agente unificado.

`run_tests` detecta o framework de testes, executa via subprocess e faz o PARSE
do resultado num resumo estruturado e legível — permitindo ao agente interpretar
falhas, sugerir correções e verificar mudanças de código (paridade com o Claude
Code).

Estratégia de parsing: em vez de raspar o texto do pytest (frágil), pedimos ao
pytest o relatório **JUnit XML** (`--junit-xml`, embutido no core do pytest, sem
plugin) e lemos o XML com `xml.etree`. Isso dá contagem confiável de
passed/failed/errors/skipped, além de arquivo/linha/nome por caso.

Tier 1 (auto-aprovado) conforme a spec `tiered-approval` — sem `interrupt_on`.
"""
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from langchain_core.tools import tool

from src.tools.self_extension import (
    _MAX_READ_CHARS,
    BACKEND_DIR,
    REPO_ROOT,
    _within_repo,
)

_TEST_TIMEOUT = int(os.getenv("TEST_TIMEOUT", "300"))
_TB_MAX_LINES = 30  # ~últimos 10 frames do traceback pytest


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _resolve_test_path(test_path: str) -> Path | None:
    """Resolve `test_path` para um caminho absoluto dentro do repo.

    Tenta relativo à raiz do repo e, se não existir, relativo ao backend/ (onde
    ficam os testes deste projeto). Retorna None se ficar fora do repo.
    """
    for base in (REPO_ROOT, BACKEND_DIR):
        candidate = (base / test_path).resolve()
        if not _within_repo(candidate):
            continue
        if candidate.exists():
            return candidate
    # Nenhum candidato existe: devolve o resolvido sob o repo (para msg de erro),
    # desde que dentro do repo.
    guess = (REPO_ROOT / test_path).resolve()
    return guess if _within_repo(guess) else None


def _detect_framework() -> str:
    """Detecta o framework a partir dos arquivos de config; fallback = pytest.

    O pytest também executa TestCases de unittest e doctests, então usamos pytest
    como runner em todos os casos — a detecção apenas nomeia o framework.
    """
    checks = {
        BACKEND_DIR / "pyproject.toml": "[tool.pytest",
        BACKEND_DIR / "pytest.ini": "[pytest]",
        BACKEND_DIR / "setup.cfg": "[tool:pytest]",
        BACKEND_DIR / "tox.ini": "[pytest]",
    }
    for cfg, marker in checks.items():
        try:
            if cfg.is_file() and marker in cfg.read_text(encoding="utf-8", errors="ignore"):
                return "pytest"
        except OSError:
            continue
    return "pytest"


def _truncate_traceback(text: str) -> str:
    """Mantém a CAUDA do traceback (onde estão a asserção/local que falhou)."""
    lines = [ln for ln in (text or "").splitlines() if ln.strip()]
    if len(lines) <= _TB_MAX_LINES:
        return "\n".join(lines)
    return "[...]\n" + "\n".join(lines[-_TB_MAX_LINES:])


def _parse_junit_xml(xml_path: Path) -> dict:
    """Faz o parse do relatório JUnit do pytest num dict estruturado.

    Retorna: {total, passed, failed, errors, skipped, duration, failures[]}.
    Cada failure: {file_path, line, test_name, failure_type, message_excerpt, traceback}.
    """
    root = ET.parse(xml_path).getroot()
    # O root pode ser <testsuites> (contendo <testsuite>) ou <testsuite>.
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    total = passed = failed = errors = skipped = 0
    duration = 0.0
    failures: list[dict] = []

    for suite in suites:
        duration += float(suite.get("time", "0") or 0)
        for case in suite.findall("testcase"):
            total += 1
            fail_el = case.find("failure")
            err_el = case.find("error")
            skip_el = case.find("skipped")
            el = fail_el if fail_el is not None else err_el
            if el is not None:
                is_error = fail_el is None
                if is_error:
                    errors += 1
                else:
                    failed += 1
                classname = case.get("classname", "")
                name = case.get("name", "")
                test_name = f"{classname}::{name}" if classname else name
                message = (el.get("message") or "").strip()
                failures.append({
                    "file_path": case.get("file", ""),
                    "line": int(case.get("line", "0") or 0),
                    "test_name": test_name,
                    "failure_type": "error" if is_error else "failure",
                    "message_excerpt": message[:300],
                    "traceback": _truncate_traceback(el.text or ""),
                })
            elif skip_el is not None:
                skipped += 1
            else:
                passed += 1

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "duration": round(duration, 2),
        "failures": failures,
    }


def _summary_header(r: dict) -> str:
    """Monta o cabeçalho legível a partir do dict estruturado."""
    total, dur = r["total"], r["duration"]
    if r["failed"] == 0 and r["errors"] == 0 and r["skipped"] == 0 and total > 0:
        return f"✅ Todos os testes passaram ({r['passed']} de {total}). Duração: {dur}s"
    parts = [f"✅ {r['passed']} passaram"]
    if r["failed"]:
        parts.append(f"❌ {r['failed']} falharam")
    if r["errors"]:
        parts.append(f"⚠️ {r['errors']} erro(s)")
    if r["skipped"]:
        parts.append(f"⏭️ {r['skipped']} ignorados")
    head = " | ".join(parts) + f"  (total: {total}, duração: {dur}s)"
    if r["failed"] or r["errors"]:
        head = f"❌ {r['failed'] + r['errors']} falharam de {total} total\n" + head
    return head


def _render(r: dict, coverage_note: str = "") -> str:
    """Renderiza o resultado estruturado num texto legível para o agente."""
    out = [_summary_header(r)]
    if coverage_note:
        out.append(coverage_note)
    for i, f in enumerate(r["failures"], start=1):
        loc = f"{f['file_path']}:{f['line']}" if f["file_path"] else "(local desconhecido)"
        out.append(
            f"\n[{i}] {f['failure_type'].upper()} — {f['test_name']}\n"
            f"    {loc}\n"
            f"    {f['message_excerpt']}"
        )
        if f["traceback"]:
            out.append("    " + f["traceback"].replace("\n", "\n    "))
    text = "\n".join(out)
    if len(text) > _MAX_READ_CHARS:
        text = text[:_MAX_READ_CHARS] + "\n\n[...truncado...]"
    return text


def _coverage_available() -> bool:
    try:
        import pytest_cov  # type: ignore[import-not-found]  # noqa: F401
        return True
    except ImportError:
        return False


def _parse_coverage(stdout: str) -> str:
    """Extrai a linha TOTAL do relatório term-missing de cobertura, se houver."""
    for line in stdout.splitlines():
        if line.strip().startswith("TOTAL"):
            return f"📊 Cobertura: {line.strip()}"
    return ""


# --------------------------------------------------------------------------- #
# run_tests
# --------------------------------------------------------------------------- #
@tool
def run_tests(test_path: str = "tests", framework: str | None = None, coverage: bool = False) -> str:
    """Executa a suíte de testes e retorna um resumo estruturado e legível.

    - `test_path`: caminho dos testes, relativo à raiz do repo ou ao backend/
      (ex.: 'backend/tests', 'tests/test_foo.py'). Padrão: 'tests'.
    - `framework`: força o framework ('pytest'); se None, é auto-detectado
      (pyproject.toml / pytest.ini / setup.cfg / tox.ini; fallback pytest).
    - `coverage`: se True e `pytest-cov` estiver instalado, adiciona `--cov=src
      --cov-report=term-missing` e inclui a % de cobertura.

    Retorna: resumo com total/passaram/falharam/erros/ignorados + duração e, por
    falha, arquivo:linha, nome do teste, tipo e trecho do traceback.
    (Tier 1 — auto-aprovado.)
    """
    target = _resolve_test_path(test_path)
    if target is None:
        return "Acesso negado: caminho fora do repositório."
    if not target.exists():
        return f"Caminho não encontrado ou sem testes: {test_path}"

    fw = (framework or _detect_framework()).lower()
    if fw != "pytest":
        # Só pytest é suportado no v1 (roda unittest/doctest também).
        fw = "pytest"

    with tempfile.TemporaryDirectory() as tmp:
        xml_path = Path(tmp) / "report.xml"
        cmd = [
            "python", "-m", "pytest", str(target),
            "-p", "no:cacheprovider",
            f"--junit-xml={xml_path}",
        ]
        if coverage and _coverage_available():
            cmd += ["--cov=src", "--cov-report=term-missing"]

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(BACKEND_DIR),
                capture_output=True,
                text=True,
                timeout=_TEST_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return f"Timeout ({_TEST_TIMEOUT}s) ao executar os testes em {test_path}."
        except OSError as exc:
            return f"Falha ao executar pytest: {exc}"

        # Exit 5 = nenhum teste coletado.
        if proc.returncode == 5:
            return f"Caminho não encontrado ou sem testes: {test_path}"
        if not xml_path.exists():
            # Erro de coleta/uso (ex.: erro de import). Devolve a saída bruta.
            out = ((proc.stdout or "") + (proc.stderr or "")).strip()
            if len(out) > _MAX_READ_CHARS:
                out = out[:_MAX_READ_CHARS] + "\n\n[...truncado...]"
            return f"❌ Falha ao coletar/rodar os testes (exit {proc.returncode}):\n{out}"

        try:
            result = _parse_junit_xml(xml_path)
        except (ET.ParseError, OSError) as exc:
            return f"Falha ao interpretar o relatório de testes: {exc}"

    cov_note = _parse_coverage(proc.stdout or "") if coverage else ""
    return _render(result, cov_note)
