"""Teste de integração: `LangGraphDirectAgentRunner` (task `agendamento-jeff-cli-task-runtime-1`).

Cobre o critério de aceite da task:

> Teste de integração: compila contra Postgres de teste, roda prompt trivial,
> confirma checkpoint gravado

Como o `unified_model` configurado em `src/agents/unified/agent.py` aponta
para Ollama Cloud + OpenRouter (modelos reais), mockamos o model dentro de
`build_unified` para isolar o teste do LLM — o que está sendo testado aqui é
o *adapter de runtime* (compilação + checkpointer/store + ainvoke), não a
execução do modelo. O grafo é o real, com `InMemorySaver` substituído por
`AsyncPostgresSaver` apontando para o Postgres de teste.

Este teste precisa de `INTEGRATION_POSTGRES_URI` apontando para um Postgres
real (tabelas precisam existir — LangGraph cria via `.setup()` no primeiro
startup da plataforma, mas aqui o runner é desenhado para NÃO chamar
`.setup()`; o teste cria as tabelas explicitamente).
"""
from __future__ import annotations

import os
from typing import Any
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

INTEGRATION_URI_ENV = "INTEGRATION_POSTGRES_URI"
pytestmark = pytest.mark.skipif(
    not os.environ.get(INTEGRATION_URI_ENV),
    reason=(
        f"Requer Postgres de teste real. Defina {INTEGRATION_URI_ENV} "
        "(ex.: postgresql://jeff_ia:jeff_ia@localhost:5436/jeff_ia) "
        "para rodar este teste."
    ),
)


class _FakeModel(GenericFakeChatModel):
    """Modelo fake — sempre responde 'olá'."""

    def bind_tools(self, tools: Any, *, tool_choice: Any = None, **kwargs: Any) -> Any:  # type: ignore[override]
        return self


async def test_langgraph_direct_runner_writes_checkpoint_to_postgres(
    tmp_path: pytest.TempPathFactory,
) -> None:
    """Cenário REQ-002 + REQ-003: o runner compila via `build_unified` (a
    mesma fábrica usada pela plataforma) e, ao rodar um prompt, persiste
    um checkpoint no Postgres para o `thread_id` informado.

    O que está sendo verificado:
    - O runner é construído sem duplicar a fábrica do grafo.
    - O `checkpointer` Postgres é aberto/fechado por invocação.
    - Após o `run`, o Postgres tem um checkpoint para o `thread_id`.

    O que está MOCKADO (e por quê):
    - `unified_model` (Ollama Cloud + OpenRouter): substituído por
      `GenericFakeChatModel` — o teste é sobre o adapter de runtime, não
      sobre a chamada real ao LLM.
    - `_build_backend_factory`: redirecionada para um `tmp_path` —
      `_UNIFIED_TOOLS` e o `ScopedSkillsMiddleware` criam diretórios
      per-thread (ex.: `.specify/specs/<thread_id>/`) no filesystem do
      host; em ambiente de teste esses paths podem ser root-owned e
      imutáveis. Apontar para `tmp_path` isola o teste de I/O de filesystem
      sem perder cobertura do contrato do adapter (compilação,
      checkpointer, ainvoke, retorno do DTO).
    """
    import uuid

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from src.agents.unified import agent as agent_module
    from src.composition.backends import FsRoute, make_backend_factory
    from src.domain.scheduling import ToolScope
    from src.infrastructure.agent_runtime.langgraph_direct_runner import (
        LangGraphDirectAgentRunner,
    )

    uri = os.environ[INTEGRATION_URI_ENV]
    # O schema do `AsyncPostgresSaver` exige `thread_id` como UUID (a coluna
    # é tipada como `UUID` no DDL interno do LangGraph). Usar string livre
    # aqui só testaria a má-formatação — não o que esta task quer verificar.
    thread_id = str(uuid.uuid4())

    # Garante que as tabelas do checkpointer existem (o runner é
    # explicitamente desenhado para NÃO chamar `.setup()`; quem cria
    # tabelas é a plataforma LangGraph no startup). Aqui é teste de
    # integração, então criamos manualmente.
    async with AsyncPostgresSaver.from_conn_string(uri) as saver:
        await saver.setup()

    # Mocka o `unified_model` para o teste não precisar de Ollama/OpenRouter
    # real. O grafo compilado continua sendo o real (`build_unified`), só
    # o model é fake.
    fake_model = _FakeModel(messages=iter([AIMessage(content="olá")]))

    # `tmp_path` isola as rotas de filesystem que `build_unified` cria
    # (`outputs/.specify/specs/<thread_id>/` etc.) do filesystem real do
    # host — em produção essas pastas são root-owned e imutáveis para o
    # usuário do teste.
    workspace = tmp_path / "workspace"
    outputs = tmp_path / "outputs"
    specify = outputs / ".specify"
    templates = tmp_path / "templates" / "sdd"
    skills = tmp_path / "skills"
    repo = tmp_path / "repo"
    for d in (workspace, outputs, specify, templates, skills, repo):
        d.mkdir(parents=True, exist_ok=True)

    def _test_backend_factory():
        return make_backend_factory(
            routes=[
                FsRoute(prefix="/workspace/", base_dir=workspace, per_thread=True),
                FsRoute(prefix="/repo/",      base_dir=repo),
                FsRoute(prefix="/outputs/",   base_dir=outputs,  per_thread=True),
                FsRoute(
                    prefix="/specify/",
                    base_dir=specify,
                    ensure_subpath="specs",
                ),
                FsRoute(prefix="/templates/", base_dir=templates),
                FsRoute(prefix="/skills/",   base_dir=skills),
            ],
            include_store=True,
        )

    with (
        patch.object(agent_module, "unified_model", fake_model),
        patch.object(
            agent_module, "_build_backend_factory", _test_backend_factory
        ),
    ):
        runner = LangGraphDirectAgentRunner(postgres_uri=uri)
        result = await runner.run(
            thread_id=thread_id,
            prompt="diga olá",
            skills=(),
            tool_scope=ToolScope.RESTRICTED,
        )

    assert result.thread_id == thread_id
    assert result.status == "ok"
    assert result.error is None

    # Confirma o checkpoint no Postgres.
    async with AsyncPostgresSaver.from_conn_string(uri) as saver:
        config = {"configurable": {"thread_id": thread_id}}
        try:
            tup = await saver.aget_tuple(config)
        except NotImplementedError:
            tup = None
        assert tup is not None, (
            f"Esperava checkpoint gravado para {thread_id}; o runner NÃO "
            "usou o checkpointer Postgres ou usou um em memória."
        )
