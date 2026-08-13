"""Testes do diff preview do Tier 3 (task `unified-dev-agent-task-frontend-2`).

O backend expõe o diff embutido no campo `description` do
`InterruptOnConfig` (langchain HITL aceita `str | Callable`). O callable
`_interrupt_description_for` é avaliado lazy — no momento do interrupt, com
o `tool_call` real. Os helpers `_diff_for_*` produzem markdown prefixado
pelo `DIFF_MARKER`, que o `ToolApprovalInterrupt` do frontend detecta.

Estes testes não dependem de LangGraph / Ollama / Postgres — só do módulo
puro. R1 do design: o interrupt nunca trava por causa do diff; toda falha
cai no fallback estático.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.agents.unified.tier_config import (
    DIFF_MARKER,
    _diff_for_edit_file,
    _diff_for_git_commit,
    _diff_for_multi_file_edit,
    _diff_for_patch_file,
    _interrupt_description_for,
    build_interrupt_on,
)


# --------------------------------------------------------------------------- #
# DIFF_MARKER — contrato backend↔frontend
# --------------------------------------------------------------------------- #
class TestDiffMarker:
    def test_marker_is_string(self):
        assert isinstance(DIFF_MARKER, str)
        assert DIFF_MARKER  # não-vazio

    def test_all_diff_helpers_start_with_marker(self):
        # O frontend detecta o diff pela presença do marcador no início da
        # string `description`. Se algum helper devolver string SEM o
        # marcador, o frontend cai no fallback (args JSON cru).
        tc = {"name": "edit_file", "args": {"path": "/nope", "old_string": "a", "new_string": "b"}}
        assert _interrupt_description_for(tc).startswith(DIFF_MARKER)

        tc = {"name": "patch_file", "args": {"path": "/nope", "diff_text": "@@ -1 +1 @@\n-a\n+b\n"}}
        assert _interrupt_description_for(tc).startswith(DIFF_MARKER)

        tc = {"name": "multi_file_edit", "args": {"edits": []}}
        # edits vazio cai no fallback (estático), sem marcador.
        assert not _interrupt_description_for(tc).startswith(DIFF_MARKER)

        tc = {"name": "git_commit", "args": {"message": "x"}}
        assert _interrupt_description_for(tc).startswith(DIFF_MARKER)


# --------------------------------------------------------------------------- #
# edit_file
# --------------------------------------------------------------------------- #
class TestEditFileDiff:
    def test_returns_diff_for_valid_args(self):
        result = _diff_for_edit_file(
            {"path": "/nope.py", "old_string": "x = 1", "new_string": "x = 2"}
        )
        assert result is not None
        assert result.startswith(DIFF_MARKER)
        assert "edit_file" in result
        assert "/nope.py" in result
        assert "```diff" in result
        # Hunk contém as duas linhas
        assert "-x = 1" in result
        assert "+x = 2" in result

    def test_includes_line_range_when_file_exists(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("# header\nx = 1\ny = 2\nz = 3\n")
            path = f.name
        try:
            result = _diff_for_edit_file(
                {"path": path, "old_string": "y = 2", "new_string": "y = 42"}
            )
            assert result is not None
            # Linha 3 (1-indexed) é onde está `y = 2`.
            assert "linhas 3" in result
        finally:
            os.unlink(path)

    def test_omits_line_range_when_path_unreadable(self):
        # Path inexistente — diff ainda sai, sem info de linha.
        result = _diff_for_edit_file(
            {"path": "/nonexistent/path.py", "old_string": "x", "new_string": "y"}
        )
        assert result is not None
        assert "linhas" not in result  # não temos info de linha

    def test_returns_none_for_invalid_args(self):
        # Faltando `path` ou tipos errados.
        assert _diff_for_edit_file({"old_string": "a", "new_string": "b"}) is None
        assert _diff_for_edit_file({"path": 123, "old_string": "a", "new_string": "b"}) is None
        assert _diff_for_edit_file({"path": "/x", "old_string": None, "new_string": "b"}) is None

    def test_truncates_very_long_diff(self):
        big = "x = 1\n" * 500  # 500 linhas
        result = _diff_for_edit_file(
            {"path": "/nope", "old_string": big, "new_string": big}
        )
        assert result is not None
        # Deve ter sido truncado.
        assert "linhas omitidas" in result


# --------------------------------------------------------------------------- #
# patch_file
# --------------------------------------------------------------------------- #
class TestPatchFileDiff:
    def test_returns_diff_with_unified_text(self):
        diff_text = "@@ -1 +1 @@\n-a\n+b\n"
        result = _diff_for_patch_file({"path": "/x.py", "diff_text": diff_text})
        assert result is not None
        assert result.startswith(DIFF_MARKER)
        assert "patch_file" in result
        assert "-a" in result
        assert "+b" in result

    def test_returns_none_for_missing_diff_text(self):
        assert _diff_for_patch_file({"path": "/x.py"}) is None
        assert _diff_for_patch_file({"path": "/x.py", "diff_text": 123}) is None


# --------------------------------------------------------------------------- #
# multi_file_edit
# --------------------------------------------------------------------------- #
class TestMultiFileEditDiff:
    def test_concatenates_hunks_with_separators(self):
        edits = [
            {"path": "a.py", "old_string": "x = 1", "new_string": "x = 2"},
            {"path": "b.py", "old_string": "y = 1", "new_string": "y = 2"},
        ]
        result = _diff_for_multi_file_edit({"edits": edits})
        assert result is not None
        assert "--- a/a.py" in result
        assert "+++ b/a.py" in result
        assert "--- a/b.py" in result
        assert "+++ b/b.py" in result

    def test_caps_at_max_files_shown(self):
        edits = [
            {"path": f"f{i}.py", "old_string": "x", "new_string": "y"}
            for i in range(10)
        ]
        result = _diff_for_multi_file_edit({"edits": edits})
        assert result is not None
        # 3 mostrados + aviso "+7".
        assert "7" in result
        assert "arquivos no diff completo" in result

    def test_returns_none_for_invalid_edits(self):
        assert _diff_for_multi_file_edit({"edits": "nope"}) is None
        assert _diff_for_multi_file_edit({"edits": []}) is None
        assert _diff_for_multi_file_edit({"edits": [{"path": "x"}]}) is None

    def test_skips_invalid_edit_entries(self):
        # Mistura: um válido, dois inválidos.
        edits = [
            {"path": "good.py", "old_string": "x", "new_string": "y"},
            {"path": 123, "old_string": "x", "new_string": "y"},  # path inválido
            "not a dict",  # não é mapping
        ]
        result = _diff_for_multi_file_edit({"edits": edits})
        assert result is not None
        assert "good.py" in result


# --------------------------------------------------------------------------- #
# git_commit
# --------------------------------------------------------------------------- #
class TestGitCommitDiff:
    def test_returns_diff_from_staged(self):
        # Sem repo git, o `git diff` falha — devolve o fallback "sem mudanças".
        result = _diff_for_git_commit({"message": "fix: x"})
        assert result is not None
        assert "git_commit" in result
        assert "fix: x" in result
        # Em um repo real (caso deste teste), pode haver ou não staged.
        # Não assertamos o conteúdo do diff — só a estrutura.

    def test_escapes_backticks_in_message(self):
        result = _diff_for_git_commit({"message": "feat: `code` in commit"})
        assert result is not None
        # Backticks no `message` devem vir escapados para não quebrar o bloco markdown.
        assert "\\`code\\`" in result

    def test_returns_none_for_invalid_message(self):
        assert _diff_for_git_commit({"message": 123}) is None
        assert _diff_for_git_commit({}) is None

    def test_handles_git_subprocess_error(self):
        # Força `subprocess.run` a levantar — verifica que o callable não trava.
        with patch(
            "src.agents.unified.tier_config.subprocess.run",
            side_effect=subprocess.SubprocessError("boom"),
        ):
            result = _diff_for_git_commit({"message": "x"})
        assert result is not None
        assert "não foi possível ler" in result


# --------------------------------------------------------------------------- #
# _interrupt_description_for — entry point callable
# --------------------------------------------------------------------------- #
class TestInterruptDescriptionFor:
    def test_unknown_tool_falls_back_to_static(self):
        # Tool não catalogada — devolve string estática, sem marcador.
        result = _interrupt_description_for({"name": "totally_unknown_tool_xyz", "args": {}})
        assert not result.startswith(DIFF_MARKER)
        assert "Aprovação humana" in result

    def test_tool_without_diff_helper_falls_back(self):
        # `delete_memory` está no TIER 3 mas NÃO tem helper de diff.
        result = _interrupt_description_for({"name": "delete_memory", "args": {"key": "x"}})
        assert not result.startswith(DIFF_MARKER)
        assert "remover" in result

    def test_helper_failure_falls_back_silently(self):
        # Se o helper levantar exceção, o callable cai no fallback.
        with patch(
            "src.agents.unified.tier_config._diff_for_edit_file",
            side_effect=RuntimeError("explodiu"),
        ):
            result = _interrupt_description_for(
                {"name": "edit_file", "args": {"path": "/x", "old_string": "a", "new_string": "b"}}
            )
        assert not result.startswith(DIFF_MARKER)

    def test_empty_args_falls_back(self):
        # edit_file sem args suficientes — helper devolve None, fallback estático.
        result = _interrupt_description_for({"name": "edit_file", "args": {}})
        assert not result.startswith(DIFF_MARKER)

    def test_ignores_state_and_runtime_args(self):
        # O langchain passa (tool_call, state, runtime) como posicionais.
        result = _interrupt_description_for(
            {"name": "edit_file", "args": {"path": "/n", "old_string": "a", "new_string": "b"}},
            {"messages": []},  # state
            "whatever",  # runtime
        )
        assert result.startswith(DIFF_MARKER)


# --------------------------------------------------------------------------- #
# build_interrupt_on — usa callable para tools com diff
# --------------------------------------------------------------------------- #
class TestBuildInterruptOnWithDiff:
    def test_tools_with_diff_get_callable_description(self):
        out = build_interrupt_on(["edit_file", "patch_file", "multi_file_edit", "git_commit"])
        for name in ("edit_file", "patch_file", "multi_file_edit", "git_commit"):
            assert name in out
            desc = out[name].get("description")
            assert callable(desc), f"{name} deveria ter description callable"

    def test_tools_without_diff_get_string_description(self):
        out = build_interrupt_on(
            ["delete_memory", "run_shell_command", "install_external_skill"]
        )
        for name in ("delete_memory", "run_shell_command", "install_external_skill"):
            assert name in out
            desc = out[name].get("description")
            assert isinstance(desc, str), f"{name} deveria ter description string"
            assert not desc.startswith(DIFF_MARKER)

    def test_callable_invocation_yields_marked_description(self):
        # Quando o langchain invocar o callable com um tool_call real, o
        # resultado deve começar com DIFF_MARKER.
        out = build_interrupt_on(["edit_file"])
        desc = out["edit_file"]["description"]
        assert callable(desc)
        result = desc(
            {"name": "edit_file", "args": {"path": "/nope", "old_string": "a", "new_string": "b"}}
        )
        assert result.startswith(DIFF_MARKER)


# --------------------------------------------------------------------------- #
# send_email (email-client-imap-mvp-task-tools-2 — REQ-005)
# --------------------------------------------------------------------------- #
class TestSendEmailDiff:
    """Aprovação do `send_email` (Tier 3) mostra um preview dos campos
    `to`/`cc`/`bcc`/subject/body antes do dispatch SMTP. Sem o preview, o
    usuário não tem como revisar o que vai sair.
    """

    def test_returns_preview_containing_all_recipients_and_body(self):
        from src.agents.unified.tier_config import _diff_for_send_email

        result = _diff_for_send_email(
            {
                "account_id": "acc-1",
                "to_addresses": ["a@example.com", "b@example.com"],
                "cc_addresses": ["c@example.com"],
                "bcc_addresses": ["d@example.com"],
                "subject": "Hello",
                "body_text": "Body content here",
                "body_html": "<p>Body content here</p>",
            }
        )
        assert result is not None
        assert result.startswith(DIFF_MARKER)
        assert "send_email" in result
        # to/cc/bcc aparecem — recipients visíveis no approval.
        assert "a@example.com" in result
        assert "b@example.com" in result
        assert "c@example.com" in result
        assert "d@example.com" in result
        # subject + body presentes.
        assert "Hello" in result
        assert "Body content here" in result
        # Bloco ```diff presente (consistente com outros helpers).
        assert "```diff" in result

    def test_renders_only_to_when_cc_bcc_absent(self):
        from src.agents.unified.tier_config import _diff_for_send_email

        result = _diff_for_send_email(
            {
                "to_addresses": ["solo@example.com"],
                "subject": "s",
                "body_text": "b",
            }
        )
        assert result is not None
        assert "solo@example.com" in result
        # cc/bcc podem ser omitidos do render (não há ninguém), mas subject
        # e body devem aparecer.
        assert "s" in result
        assert "b" in result

    def test_returns_none_for_missing_required_fields(self):
        from src.agents.unified.tier_config import _diff_for_send_email

        # Falta `to_addresses`.
        assert (
            _diff_for_send_email(
                {"subject": "s", "body_text": "b"}
            )
            is None
        )
        # Tipos errados.
        assert (
            _diff_for_send_email(
                {"to_addresses": "not a list", "subject": "s", "body_text": "b"}
            )
            is None
        )
        # Sem corpo algum (nem text nem html).
        assert (
            _diff_for_send_email(
                {"to_addresses": ["a@example.com"], "subject": "s"}
            )
            is None
        )
        # `to_addresses` vazio não é "missing" — ainda assim não devemos
        # renderizar um send sem destinatário, mas a função renderiza e o
        # backend recusa o envio em outro lugar.

    def test_html_only_body_still_renders_preview(self):
        """HTML-first: body_text omitido não deve cair no preview estático."""
        from src.agents.unified.tier_config import _diff_for_send_email

        result = _diff_for_send_email(
            {
                "to_addresses": ["a@example.com"],
                "subject": "Hello",
                "body_html": "<p>Hi there</p>",
            }
        )
        assert result is not None
        assert "Hi there" in result
        assert "corpo (html)" in result

    def test_truncates_very_long_body(self):
        from src.agents.unified.tier_config import _diff_for_send_email

        big = "x\n" * 500
        result = _diff_for_send_email(
            {
                "to_addresses": ["a@example.com"],
                "subject": "s",
                "body_text": big,
            }
        )
        assert result is not None
        # O body grande deve ter sido truncado com aviso, consistente com
        # `_diff_for_edit_file` (que produz "linhas omitidas").
        assert "omitid" in result.lower() or "truncad" in result.lower()

    def test_escapes_backticks_in_subject_or_body(self):
        from src.agents.unified.tier_config import _diff_for_send_email

        result = _diff_for_send_email(
            {
                "to_addresses": ["a@example.com"],
                "subject": "feat: `code` here",
                "body_text": "see `foo`",
            }
        )
        assert result is not None
        # Backticks no subject/body devem vir escapados para não quebrar o bloco markdown.
        assert "\\`code\\`" in result
        assert "\\`foo\\`" in result


class TestSendEmailTierAndRegistration:
    """`send_email` deve estar em Tier 3 e registrado em `_DIFF_HELPERS`."""

    def test_send_email_is_tier_3(self):
        from src.agents.unified.tier_config import TIER_3_TOOLS, TIER_REGISTRY

        assert "send_email" in TIER_3_TOOLS
        assert TIER_REGISTRY["send_email"] == 3

    def test_send_email_is_in_diff_helpers(self):
        from src.agents.unified.tier_config import _DIFF_HELPERS

        assert "send_email" in _DIFF_HELPERS
        # O nome do helper é resolvido via globals() — string, não callable.
        assert _DIFF_HELPERS["send_email"] == "_diff_for_send_email"

    def test_interrupt_description_for_send_email_returns_marked_preview(self):
        # Quando o langchain invoca o callable com tool_call real, o helper
        # deve produzir string prefixada com DIFF_MARKER (mesma forma que
        # os outros helpers Tier 3 — frontend detecta pelo prefixo).
        result = _interrupt_description_for(
            {
                "name": "send_email",
                "args": {
                    "to_addresses": ["a@example.com"],
                    "subject": "hi",
                    "body_text": "hello",
                },
            }
        )
        assert result.startswith(DIFF_MARKER)
        assert "send_email" in result

    def test_build_interrupt_on_gives_send_email_callable_description(self):
        from src.agents.unified.tier_config import build_interrupt_on

        out = build_interrupt_on(["send_email"])
        assert "send_email" in out
        desc = out["send_email"].get("description")
        assert callable(desc), "send_email deveria ter description callable"
        # Callable executa e produz preview marcado.
        rendered = desc(
            {
                "name": "send_email",
                "args": {
                    "to_addresses": ["a@example.com"],
                    "subject": "hi",
                    "body_text": "hello",
                },
            }
        )
        assert rendered.startswith(DIFF_MARKER)


# --------------------------------------------------------------------------- #
# _read_text_safely — file reading helper
# --------------------------------------------------------------------------- #
class TestReadTextSafely:
    def test_returns_none_for_nonexistent(self):
        from src.agents.unified.tier_config import _read_text_safely
        assert _read_text_safely("/nonexistent/path/12345.py") is None

    def test_returns_none_for_directory(self):
        from src.agents.unified.tier_config import _read_text_safely
        assert _read_text_safely("/tmp") is None

    def test_reads_real_file(self):
        from src.agents.unified.tier_config import _read_text_safely
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("hello")
            path = f.name
        try:
            content = _read_text_safely(path)
            assert content == "hello"
        finally:
            os.unlink(path)
