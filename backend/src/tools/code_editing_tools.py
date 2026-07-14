"""Ferramentas de edição cirúrgica de código no repositório REAL.

Diferente de `read_project_file`/`list_project_files` (somente leitura) e de
`write_file`/`read_file` do deepagents (que operam no WORKSPACE_DIR isolado),
estas ferramentas ESCREVEM diretamente no repositório sob controle de versão
(`REPO_ROOT`). São a capacidade central que faltava frente ao Claude Code.

Quatro ferramentas, todas com trilhos de segurança:

1. `edit_file`  — substituição exata de string ÚNICA no arquivo, atômica.
                  Ambiguidade (N>1 ocorrências) é ERRO — nada é escrito.
2. `patch_file` — aplica um unified diff, validando todos os hunks antes (all-or-nothing).
3. `grep_project` — busca regex estruturada no projeto (pula binários e >1MB).
4. `multi_file_edit` — edições em lote, validando TODAS antes de aplicar QUALQUER uma.
                  Várias edições no MESMO arquivo são acumuladas, não concorrentes.

Todas respeitam o limite do repositório (`_within_repo` / `REPO_ROOT`) e usam
escrita atômica (`tempfile` + `os.replace`) que PRESERVA O MODO do arquivo.
Edições (edit/patch/multi) são de Tier 3 (interrupt_on) conforme a spec
`tiered-approval` — o gate de aprovação é aplicado na montagem do grafo.
"""
import fnmatch
import os
import re
import tempfile
from pathlib import Path

from langchain_core.tools import tool

from src.tools.self_extension import _IGNORE, REPO_ROOT, _within_repo

# Limites de segurança para varredura de arquivos.
_MAX_FILE_BYTES = 1_000_000  # arquivos > 1MB são pulados no grep
_GREP_MAX_RESULTS = 50
_PATH_DENIED = "Acesso negado: caminho fora do repositório."


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _resolve_in_repo(path: str) -> Path | None:
    """Resolve `path` (relativo ao REPO_ROOT) e garante que fica dentro do repo.

    Retorna o Path resolvido ou None se estiver fora do repositório.
    """
    target = (REPO_ROOT / path).resolve()
    return target if _within_repo(target) else None


def _atomic_write(target: Path, content: str) -> None:
    """Escreve `content` em `target` atomicamente (tempfile no mesmo dir + os.replace).

    PRESERVA O MODO DO ARQUIVO. `tempfile.mkstemp` cria com 0600, e `os.replace`
    move o inode do temporário para o lugar do alvo — levando junto o modo 0600.
    Sem o `chmod` abaixo, editar um script com bit de execução (`0755`) o deixa
    não-executável, e um arquivo legível por outros passa a ser 0600.
    """
    try:
        mode: int | None = target.stat().st_mode & 0o7777
    except OSError:
        mode = None  # arquivo novo: deixa o umask decidir

    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        # Não deixa lixo para trás se algo falhar antes/depois do replace.
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _is_binary(data: bytes) -> bool:
    """Heurística simples: presença de byte nulo indica arquivo binário."""
    return b"\x00" in data


# --------------------------------------------------------------------------- #
# 1. edit_file — substituição exata da primeira ocorrência
# --------------------------------------------------------------------------- #
@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """Substitui a ÚNICA ocorrência exata de `old_string` por `new_string` num arquivo.

    Edição cirúrgica no repositório REAL (não no workspace isolado). `path` é
    relativo à raiz do repo (ex.: 'backend/src/tools/example.py'). A escrita é
    atômica e preserva o modo do arquivo.

    `old_string` DEVE ser único no arquivo. Se não existir, ou se aparecer mais de
    uma vez, NADA é alterado e um erro é retornado — inclua linhas de contexto ao
    redor para desambiguar.

    Requer aprovação humana (Tier 3) antes de aplicar.
    """
    target = _resolve_in_repo(path)
    if target is None:
        return _PATH_DENIED
    if not target.is_file():
        return f"Arquivo não encontrado: {path}"

    content = target.read_text(encoding="utf-8")
    occurrences = content.count(old_string)
    if occurrences == 0:
        return (
            f"[SEM ALTERAÇÃO] `old_string` não encontrado em {path}. "
            "Verifique o conteúdo atual do arquivo (read_project_file) e tente de novo."
        )
    # Ambiguidade é ERRO, não aviso. Editar "a primeira das N" quando o chamador
    # não disse qual queria é escolher por ele — e reportar [OK] depois de ter
    # possivelmente editado o lugar errado. `multi_file_edit` já rejeitava isso;
    # aqui a regra é a mesma.
    if occurrences > 1:
        return (
            f"[SEM ALTERAÇÃO] `old_string` aparece {occurrences}x em {path} — "
            "é ambíguo qual delas editar. Inclua linhas de contexto ao redor para "
            "tornar o trecho único. Nenhuma alteração foi feita."
        )

    idx = content.find(old_string)
    _atomic_write(target, content.replace(old_string, new_string, 1))

    line_number = content.count("\n", 0, idx) + 1
    return f"[OK] Editado {path} (linha {line_number})."


# --------------------------------------------------------------------------- #
# 2. patch_file — aplica unified diff (all-or-nothing)
# --------------------------------------------------------------------------- #
_HUNK_HEADER_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _parse_hunks(diff_text: str) -> tuple[list[dict], str | None]:
    r"""Extrai os hunks de um unified diff.

    Retorna (hunks, erro). Cada hunk: {old_start, old_lines[], new_lines[]}, onde
    `old_lines` são as linhas do lado original (contexto + removidas) e `new_lines`
    as do lado novo (contexto + adicionadas). Linhas de cabeçalho de arquivo
    (`---`, `+++`, `diff`, `index`) e marcadores de "no newline" (`\\`) são ignorados.
    """
    hunks: list[dict] = []
    current: dict | None = None
    for raw in diff_text.splitlines():
        header = _HUNK_HEADER_RE.match(raw)
        if header:
            current = {
                "old_start": int(header.group(1)),
                "old_lines": [],
                "new_lines": [],
            }
            hunks.append(current)
            continue
        if current is None:
            # Ainda não entramos num hunk: pula cabeçalhos de arquivo/metadados.
            continue
        if not raw:
            # Linha vazia dentro do diff representa uma linha de contexto vazia.
            current["old_lines"].append("")
            current["new_lines"].append("")
            continue
        tag, text = raw[0], raw[1:]
        if tag == " ":
            current["old_lines"].append(text)
            current["new_lines"].append(text)
        elif tag == "-":
            current["old_lines"].append(text)
        elif tag == "+":
            current["new_lines"].append(text)
        elif tag == "\\":
            # "\ No newline at end of file" — não afeta o conteúdo das linhas.
            continue
        else:
            return [], f"Linha de diff inválida (prefixo {tag!r}): {raw!r}"
    if not hunks:
        return [], "Nenhum hunk encontrado no diff (esperado cabeçalho '@@ -l,s +l,s @@')."
    return hunks, None


@tool
def patch_file(path: str, diff_text: str) -> str:
    """Aplica um unified diff a um arquivo do repositório, de forma atômica e all-or-nothing.

    `path` é relativo à raiz do repo. `diff_text` é um unified diff (linhas de
    contexto começam com ' ', removidas com '-', adicionadas com '+', hunks com
    '@@ -l,s +l,s @@'). TODOS os hunks são validados contra o conteúdo atual antes
    de qualquer escrita; se algum hunk não casar, NADA é alterado e o erro indica
    qual hunk falhou.

    Requer aprovação humana (Tier 3) antes de aplicar.
    """
    target = _resolve_in_repo(path)
    if target is None:
        return _PATH_DENIED
    if not target.is_file():
        return f"Arquivo não encontrado: {path}"

    hunks, err = _parse_hunks(diff_text)
    if err is not None:
        return f"[PATCH INVÁLIDO] {err}"

    original = target.read_text(encoding="utf-8")
    ends_with_newline = original.endswith("\n")
    lines = original.split("\n")
    if ends_with_newline:
        # split deixa um "" final quando o texto termina em \n; remove para casar
        # com a contagem real de linhas.
        lines.pop()

    result: list[str] = []
    cursor = 0  # índice 0-based na lista `lines` já consumido
    for i, hunk in enumerate(hunks, start=1):
        start = hunk["old_start"] - 1  # 1-based → 0-based
        if start < cursor:
            return (
                f"[PATCH REJEITADO] Hunk #{i} sobrepõe ou está fora de ordem "
                f"(início na linha {hunk['old_start']})."
            )
        if start > len(lines):
            return (
                f"[PATCH REJEITADO] Hunk #{i} começa na linha {hunk['old_start']}, "
                f"mas o arquivo tem apenas {len(lines)} linhas."
            )
        # Copia as linhas intactas antes do hunk.
        result.extend(lines[cursor:start])
        # Valida cada linha do lado original contra o arquivo.
        old = hunk["old_lines"]
        actual = lines[start:start + len(old)]
        if actual != old:
            return (
                f"[PATCH REJEITADO] Hunk #{i} não casa com o conteúdo atual de {path} "
                f"(linha {hunk['old_start']}). Nenhuma alteração foi feita."
            )
        # Aplica o lado novo.
        result.extend(hunk["new_lines"])
        cursor = start + len(old)

    # Linhas remanescentes após o último hunk.
    result.extend(lines[cursor:])

    new_content = "\n".join(result)
    if ends_with_newline:
        new_content += "\n"
    _atomic_write(target, new_content)
    return f"[OK] Patch aplicado em {path} ({len(hunks)} hunk(s))."


# --------------------------------------------------------------------------- #
# 3. grep_project — busca regex estruturada
# --------------------------------------------------------------------------- #
@tool
def grep_project(pattern: str, path: str = ".", include: str = "*.py") -> str:
    """Busca `pattern` (regex) nos arquivos do projeto e retorna resultados estruturados.

    `path` é relativo à raiz do repo (padrão: raiz). `include` é um glob de nome de
    arquivo (padrão: '*.py'; use '*' para todos). Retorna linhas no formato
    `caminho:linha: trecho`, limitado a 50 resultados. Diretórios pesados (.git,
    node_modules, __pycache__, ...) são ignorados; arquivos binários e > 1MB são pulados.
    """
    try:
        regex = re.compile(pattern)
    except re.error as exc:
        return f"Regex inválida: {exc}"

    base = _resolve_in_repo(path)
    if base is None:
        return _PATH_DENIED
    if not base.exists():
        return f"Não encontrado: {path}"

    results: list[str] = []
    skipped = 0
    truncated = False

    files: list[Path]
    if base.is_file():
        files = [base]
    else:
        files = sorted(p for p in base.rglob("*") if p.is_file())

    for fpath in files:
        # Pula diretórios ignorados em qualquer nível do caminho.
        if any(part in _IGNORE for part in fpath.parts):
            continue
        if not fnmatch.fnmatch(fpath.name, include):
            continue
        try:
            if fpath.stat().st_size > _MAX_FILE_BYTES:
                skipped += 1
                continue
            raw = fpath.read_bytes()
        except OSError:
            continue
        if _is_binary(raw):
            skipped += 1
            continue

        rel = fpath.relative_to(REPO_ROOT)
        text = raw.decode("utf-8", errors="replace")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                results.append(f"{rel}:{lineno}: {line.strip()}")
                if len(results) >= _GREP_MAX_RESULTS:
                    truncated = True
                    break
        if truncated:
            break

    if not results:
        note = f" ({skipped} arquivo(s) binário(s)/grande(s) pulado(s))" if skipped else ""
        return f"Nenhum resultado encontrado para '{pattern}'{note}."

    header = f"{len(results)} resultado(s) para '{pattern}':"
    footer = ""
    if truncated:
        footer = f"\n[...limitado a {_GREP_MAX_RESULTS} resultados...]"
    if skipped:
        footer += f"\n({skipped} arquivo(s) binário(s)/grande(s) pulado(s))"
    return header + "\n" + "\n".join(results) + footer


# --------------------------------------------------------------------------- #
# 4. multi_file_edit — lote atômico (valida tudo antes de aplicar)
# --------------------------------------------------------------------------- #
@tool
def multi_file_edit(edits: list[dict]) -> str:
    """Aplica várias edições exatas em lote, validando TODAS antes de aplicar QUALQUER uma.

    `edits` é uma lista de dicionários `{"path", "old_string", "new_string"}`. Cada
    `old_string` DEVE existir EXATAMENTE uma vez em seu arquivo. Se todas as edições
    forem válidas, todas são aplicadas (escrita atômica por arquivo); se QUALQUER
    uma for inválida, NENHUMA é aplicada e o erro indica qual falhou.

    Ideal para refatorações que tocam múltiplos arquivos. Requer aprovação humana
    (Tier 3) antes de aplicar.
    """
    if not edits:
        return "Nenhuma edição fornecida."

    # Conteúdo em construção, ACUMULADO por arquivo. Antes, cada edição era
    # calculada sobre o conteúdo lido do disco; duas edições no mesmo arquivo
    # geravam duas versões concorrentes do original e a última escrita descartava
    # a primeira — silenciosamente, reportando "[OK] 2 edições aplicadas".
    # Acumular aqui faz cada edição enxergar o resultado da anterior.
    pending: dict[Path, str] = {}
    order: list[Path] = []

    for i, edit in enumerate(edits, start=1):
        if not isinstance(edit, dict):
            return f"[LOTE REJEITADO] Edição #{i} não é um objeto {{path, old_string, new_string}}."
        path = edit.get("path")
        old_string = edit.get("old_string")
        new_string = edit.get("new_string")
        if not path or old_string is None or new_string is None:
            return (
                f"[LOTE REJEITADO] Edição #{i} incompleta: "
                "requer 'path', 'old_string' e 'new_string'."
            )

        target = _resolve_in_repo(path)
        if target is None:
            return f"[LOTE REJEITADO] Edição #{i}: {_PATH_DENIED} ({path})"
        if not target.is_file():
            return f"[LOTE REJEITADO] Edição #{i}: arquivo não encontrado: {path}"

        if target not in pending:
            pending[target] = target.read_text(encoding="utf-8")
            order.append(target)

        content = pending[target]
        count = content.count(old_string)
        if count == 0:
            return (
                f"[LOTE REJEITADO] Edição #{i}: `old_string` não encontrado em {path}. "
                "Nenhuma alteração foi feita."
            )
        if count > 1:
            return (
                f"[LOTE REJEITADO] Edição #{i}: `old_string` aparece {count}x em {path} "
                "(deve ser único). Use um trecho mais específico. Nenhuma alteração foi feita."
            )
        pending[target] = content.replace(old_string, new_string, 1)

    # Todas validadas → aplica, um write por arquivo.
    for target in order:
        _atomic_write(target, pending[target])

    paths = ", ".join(str(t.relative_to(REPO_ROOT)) for t in order)
    return (
        f"[OK] {len(edits)} edição(ões) aplicada(s) atomicamente "
        f"em {len(order)} arquivo(s): {paths}"
    )
