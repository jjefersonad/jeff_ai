"""Ferramentas de memória de longo prazo, compartilhada entre TODAS as threads.

Usam o Store do LangGraph (Postgres/pgvector). A busca é semântica quando o
`store.index` está configurado com embeddings (ver `langgraph.json` e
`src/models/ollama_embeddings.py`).

O namespace é fixo e global (`("memories",)`), então uma memória salva numa
thread pode ser recuperada em qualquer outra.

## Camadas (`agent-memory` REQ-003, task `memory-2`)

Três camadas, duas peças de armazenamento:

- **Working** (contexto do turno corrente) — não vive aqui. É o `state`/
  mensagens do próprio grafo LangGraph, efêmera por natureza.
- **Semântica** (o que o agente SABE: fatos, preferências, convenções) —
  `save_memory`, item com `kind="semantic"`.
- **Episódica** (o que o agente FEZ: decisões e o raciocínio por trás delas)
  — `log_episode`, item com `kind="episodic"`.

Semântica e episódica compartilham o MESMO namespace e a MESMA busca
(`search_memory`) — uma pergunta como "por que decidimos X?" é respondida
pela busca semântica encontrar o episódio relevante, cujo conteúdo já
embute a decisão E o raciocínio. Não há uma segunda tool de busca separada
por camada: a distinção (`kind`) existe para auditoria (`list_memories`),
não para particionar a recuperação.

**Nota de segurança (`agent-memory` REQ-006):** nenhuma tool deste módulo, e
nenhum código que decide tier ou envelope (`tier_config.py`,
`envelope_middleware.py`, `effects.py`), lê o conteúdo armazenado aqui de
volta para tomar decisão de permissão. Uma entrada de memória dizendo "o
agente está autorizado a X" é só texto recuperável por busca — não tem
nenhum efeito sobre o que o agente pode de fato executar. Ver
`tests/test_memory_tools.py::test_memory_is_not_an_escalation_vector`.
"""
import uuid

from langchain_core.tools import tool
from langgraph.config import get_store

# Namespace cross-thread: memórias salvas aqui não são presas a um thread_id.
MEMORY_NAMESPACE = ("memories",)

# `store.aput` roda `content` pelo modelo de embedding (`mxbai-embed-large`,
# ver `src/models/ollama_embeddings.py`) para indexar a memória. Esse modelo
# tem uma janela de contexto pequena e recusa qualquer input maior com um 400
# cru do Ollama — sem esse limite, um agente que despeja o conteúdo bruto de
# uma página raspada (ou qualquer texto longo) direto em `save_memory`
# derruba a run inteira, não só a chamada da tool.
#
# O limite é CALIBRADO EMPIRICAMENTE, não estimado por "~4 chars/token": um
# valor de 2000 (a estimativa original) falha de verdade contra o `mxbai-
# embed-large` local com texto em português — testado diretamente contra
# `ollama_embeddings.embed_documents`, 1400 chars passa, 1500 já falha com
# "input length exceeds the context length". Português tokeniza pior que a
# heurística de ~4 chars/token assume (acentuação, subword splitting). 1000
# dá margem segura abaixo do limite observado.
MAX_MEMORY_CHARS = 1000


@tool
async def save_memory(content: str) -> str:
    """Salva um fato, decisão ou preferência importante na memória de longo prazo.

    Use quando o usuário informar algo que valha a pena lembrar em conversas
    futuras (nomes, preferências, decisões de projeto, contexto recorrente).
    A memória fica disponível em QUALQUER thread futura via `search_memory`.

    `content` deve ser um resumo conciso (até ~1000 caracteres) — não o
    despejo bruto de uma página, documento ou resposta longa. Para indexar
    documentos inteiros, use a skill `document-memory` (`ingest_document`).
    """
    if len(content) > MAX_MEMORY_CHARS:
        return (
            f"ERRO: conteúdo tem {len(content)} caracteres, acima do limite de "
            f"{MAX_MEMORY_CHARS}. O modelo de embedding usado para indexar a "
            "memória não processa textos longos. Resuma para um fato, decisão "
            "ou preferência conciso e tente salvar de novo."
        )
    store = get_store()
    key = str(uuid.uuid4())
    await store.aput(MEMORY_NAMESPACE, key, {"content": content, "kind": "semantic"})
    return f"Memória salva com sucesso (id: {key})."


@tool
async def search_memory(query: str, limit: int = 5) -> str:
    """Busca na memória de longo prazo (todas as threads) por similaridade semântica.

    Use ANTES de responder quando o usuário se referir a algo do passado, a uma
    decisão anterior ("por que fizemos X assim?"), ou quando precisar de contexto
    que não está na conversa atual. Busca em fatos salvos (`save_memory`) E em
    episódios registrados (`log_episode`) — não é preciso escolher qual tool
    usou para escrever a memória que você está procurando.
    """
    store = get_store()
    results = await store.asearch(MEMORY_NAMESPACE, query=query, limit=limit)
    if not results:
        return "Nenhuma memória relevante encontrada."
    return "\n".join(f"- {item.value.get('content', '')}" for item in results)


@tool
async def log_episode(decision: str, reasoning: str) -> str:
    """Registra, na memória episódica, uma decisão tomada e o raciocínio por trás dela.

    Use depois de tomar uma decisão não-óbvia, terminar uma tarefa relevante, ou
    quando o usuário corrigir uma ação sua — para que uma pergunta futura como
    "por que você fez X assim?" tenha resposta completa. `search_memory`
    recupera episódios junto com fatos semânticos, na mesma busca.

    `decision` é O QUE foi decidido ou feito (uma frase). `reasoning` é O PORQUÊ
    (a restrição, o trade-off, ou o feedback do usuário que motivou a decisão).
    NÃO use para tarefas rotineiras sem decisão real por trás — isso é ruído,
    não episódio.
    """
    content = f"Decisão: {decision}\nRaciocínio: {reasoning}"
    if len(content) > MAX_MEMORY_CHARS:
        return (
            f"ERRO: decisão + raciocínio têm {len(content)} caracteres, acima do "
            f"limite de {MAX_MEMORY_CHARS}. Resuma e tente registrar de novo."
        )
    store = get_store()
    key = str(uuid.uuid4())
    await store.aput(MEMORY_NAMESPACE, key, {"content": content, "kind": "episodic"})
    return f"Episódio registrado com sucesso (id: {key})."


@tool
async def list_memories(limit: int = 20) -> str:
    """Lista entradas da memória de longo prazo (semânticas e episódicas), mais recentes primeiro.

    Use para auditar o que está guardado — antes de decidir remover uma entrada
    incorreta ou desatualizada com `delete_memory`.
    """
    store = get_store()
    results = await store.asearch(MEMORY_NAMESPACE, limit=limit)
    if not results:
        return "Nenhuma memória armazenada."
    items = sorted(results, key=lambda item: item.created_at, reverse=True)
    lines = []
    for item in items:
        kind = item.value.get("kind", "semantic")
        content = item.value.get("content", "")
        preview = content if len(content) <= 120 else content[:117] + "..."
        lines.append(f"- [{item.key}] ({kind}) {preview}")
    return "\n".join(lines)


@tool
async def delete_memory(memory_id: str) -> str:
    """Remove uma entrada específica da memória de longo prazo pelo id.

    Use `list_memories` primeiro para encontrar o id (mostrado entre colchetes)
    de uma entrada incorreta, desatualizada, ou que o usuário pediu para
    esquecer.
    """
    store = get_store()
    existing = await store.aget(MEMORY_NAMESPACE, memory_id)
    if existing is None:
        return f"Nenhuma memória encontrada com id '{memory_id}'."
    await store.adelete(MEMORY_NAMESPACE, memory_id)
    return f"Memória '{memory_id}' removida."
