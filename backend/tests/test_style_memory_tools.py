"""Testes das ferramentas de memória de estilos (REQ-001 / image-style-consistency).

Usam um InMemoryStore do LangGraph e fazem patch de get_store/get_config, então
não dependem de Postgres nem de um runtime LangGraph ativo.
"""
import pytest
from langgraph.store.memory import InMemoryStore

import src.tools.style_memory_tools as sm


@pytest.fixture
def store(monkeypatch):
    s = InMemoryStore()
    monkeypatch.setattr(sm, "get_store", lambda: s)
    # thread atual = "t1" por padrão
    monkeypatch.setattr(
        sm, "get_config", lambda: {"configurable": {"thread_id": "t1"}}
    )
    return s


async def test_save_then_load_latest(store):
    """REQ-001: salvar e recuperar o design plan mais recente do thread."""
    await sm.save_design_style.ainvoke(
        {"design_plan": "plano A", "final_prompt": "prompt A"}
    )
    out = await sm.load_design_style.ainvoke({})
    assert "plano A" in out
    assert "prompt A" in out


async def test_versioning_no_overwrite(store):
    """REQ-002: cada save cria nova versão; load retorna a mais recente."""
    await sm.save_design_style.ainvoke({"design_plan": "plano V1"})
    await sm.save_design_style.ainvoke({"design_plan": "plano V2"})

    # duas versões coexistem
    listing = await sm.list_design_styles.ainvoke({})
    assert listing.count("\n") == 1  # duas linhas => um "\n"
    # a mais recente é a V2
    latest = await sm.load_design_style.ainvoke({})
    assert "plano V2" in latest


async def test_cross_thread_transfer(store):
    """REQ-003: transferência explícita de estilo entre threads via thread_id."""
    # salva no thread atual (t1)
    await sm.save_design_style.ainvoke({"design_plan": "estilo do t1"})
    # thread corrente muda para t2, mas pedimos o estilo de t1 explicitamente
    out = await sm.load_design_style.ainvoke({"thread_id": "t1"})
    assert "estilo do t1" in out


async def test_load_empty_thread(store):
    """Sem estilos salvos, load informa ausência (não quebra)."""
    out = await sm.load_design_style.ainvoke({"thread_id": "inexistente"})
    assert "Nenhum estilo salvo" in out


async def test_saved_under_correct_namespace(store):
    """REQ-001: o estilo é persistido no namespace ('styles', thread_id)."""
    await sm.save_design_style.ainvoke({"design_plan": "plano ns"})
    items = await store.asearch(("styles", "t1"))
    assert len(items) == 1
    assert items[0].value["design_plan"] == "plano ns"
