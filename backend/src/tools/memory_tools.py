"""Ferramentas de memória de longo prazo, compartilhada entre threads do mesmo usuário.

Usam o Store do LangGraph (Postgres/pgvector). A busca é semântica quando o
`store.index` está configurado com embeddings (ver `langgraph.json` e
`src/models/ollama_embeddings.py`).

O namespace é `("memories", <user_id>)` quando o overlay de perfil é
no-op, e `("memories", <user_id>, <profile_id>)` quando
`AgentProfileMiddleware` publicou um snapshot validado (task
`multi-agent-profiles-runtime-task-memory-1`). Chat e scheduled run do
mesmo par compartilham o namespace de 3 segmentos. Sem cópia, merge ou
search no namespace legado. `<user_id>` vem de
`ownership.store.resolve_user_id()`, o resolvedor canônico
`user_key → user_id` (mesmo usado por `record_ownership` e pelo
middleware de MCP) — funciona tanto para sessões `web:` quanto para uma
sessão `telegram:<chat_id>` já vinculada via `user_integrations`. Sem
`user_id` resolvível (sessão não-autenticada ou chat Telegram ainda não
vinculado), as tools falham fechado: recusam a operação em vez de cair de
volta a um namespace compartilhado.

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
from langgraph.config import get_config, get_store

from src.agents.unified.agent_profile_middleware import get_current_agent_profile
from src.infrastructure.ownership.store import resolve_user_id

# Prefixo do namespace cross-thread: memórias salvas aqui não são presas a um
# thread_id, mas SÃO presas a um usuário (e, com overlay, ao perfil) — o
# namespace efetivo é `MEMORY_NAMESPACE + (user_id,)` ou
# `MEMORY_NAMESPACE + (user_id, profile_id)` (ver `_resolve_namespace`).
MEMORY_NAMESPACE = ("memories",)

_NO_IDENTITY_MESSAGE = (
    "Não foi possível acessar a memória de longo prazo: esta sessão não tem "
    "identidade de usuário (não autenticada). Faça login na web antes de usar "
    "esta ferramenta."
)

_CHANNEL_UNLINKED_MESSAGE = (
    "Não foi possível acessar a memória de longo prazo: este canal "
    "(Telegram/WhatsApp) ainda não está vinculado a uma conta. Vincule a "
    "conta nas integrações antes de usar esta ferramenta."
)

# Alias legado — preferir `_message_for_unresolved_user()`.
_NO_USER_MESSAGE = _NO_IDENTITY_MESSAGE


def _message_for_unresolved_user() -> str:
    """Mensagem tipada quando `resolve_user_id()` é `None` (REQ-004 delta)."""
    user_key = get_config().get("configurable", {}).get("user_key")
    if isinstance(user_key, str) and (
        user_key.startswith("telegram:") or user_key.startswith("whatsapp:")
    ):
        return _CHANNEL_UNLINKED_MESSAGE
    return _NO_IDENTITY_MESSAGE


def _overlay_profile_id() -> str | None:
    """UUID do snapshot de perfil, ou `None` se o overlay é no-op."""
    profile = get_current_agent_profile()
    if profile is None:
        return None
    return profile.id


def _exact_namespace_items(results: list, namespace: tuple[str, ...]) -> list:
    """O `store.search`/`asearch` é prefix-match.

    Sem este corte, `("memories", user_id)` devolveria também
    `("memories", user_id, profile_id)` — misturaria overlay e legado.
    """
    return [item for item in results if tuple(item.namespace) == namespace]


async def _asearch_exact(
    store,
    namespace: tuple[str, ...],
    *,
    query: str | None = None,
    limit: int,
) -> list:
    """Busca e descarta itens de namespaces filhos (prefix leak)."""
    fetched = await store.asearch(
        namespace, query=query, limit=max(limit * 20, 50)
    )
    return _exact_namespace_items(fetched, namespace)[:limit]


async def _resolve_namespace() -> tuple[str, ...] | None:
    """Namespace efetivo desta chamada, ou `None` se não há usuário resolvível.

    Fail-closed (REQ-006 cenário 2): nenhuma tool deste módulo cai de volta a
    `MEMORY_NAMESPACE` sozinho quando `resolve_user_id()` devolve `None`.

    Overlay ativo (snapshot publicado pelo `AgentProfileMiddleware`):
    `("memories", user_id, profile_id)`. Sem overlay: `("memories", user_id)`.
    Não consulta o namespace legado como fallback.
    """
    user_id = await resolve_user_id()
    if user_id is None:
        return None
    profile_id = _overlay_profile_id()
    if profile_id is None:
        return (*MEMORY_NAMESPACE, user_id)
    return (*MEMORY_NAMESPACE, user_id, profile_id)


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
    A memória fica disponível nas threads futuras do mesmo usuário via
    `search_memory`; com overlay de perfil, só nesse perfil (não no
    namespace legado nem em outro `user_id`).

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
    namespace = await _resolve_namespace()
    if namespace is None:
        return _message_for_unresolved_user()
    store = get_store()
    key = str(uuid.uuid4())
    await store.aput(namespace, key, {"content": content, "kind": "semantic"})
    return f"Memória salva com sucesso (id: {key})."


@tool
async def search_memory(query: str, limit: int = 5) -> str:
    """Busca na memória de longo prazo (threads do mesmo usuário/perfil) por similaridade semântica.

    Use ANTES de responder quando o usuário se referir a algo do passado, a uma
    decisão anterior ("por que fizemos X assim?"), ou quando precisar de contexto
    que não está na conversa atual. Busca em fatos salvos (`save_memory`) E em
    episódios registrados (`log_episode`) — não é preciso escolher qual tool
    usou para escrever a memória que você está procurando. Com overlay de
    perfil, não mistura o namespace legado nem memórias de outro usuário.
    """
    namespace = await _resolve_namespace()
    if namespace is None:
        return _message_for_unresolved_user()
    store = get_store()
    results = await _asearch_exact(store, namespace, query=query, limit=limit)
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
    namespace = await _resolve_namespace()
    if namespace is None:
        return _message_for_unresolved_user()
    store = get_store()
    key = str(uuid.uuid4())
    await store.aput(namespace, key, {"content": content, "kind": "episodic"})
    return f"Episódio registrado com sucesso (id: {key})."


@tool
async def list_memories(limit: int = 20) -> str:
    """Lista entradas da memória de longo prazo (semânticas e episódicas), mais recentes primeiro.

    Use para auditar o que está guardado — antes de decidir remover uma entrada
    incorreta ou desatualizada com `delete_memory`.
    """
    namespace = await _resolve_namespace()
    if namespace is None:
        return _message_for_unresolved_user()
    store = get_store()
    results = await _asearch_exact(store, namespace, limit=limit)
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
    namespace = await _resolve_namespace()
    if namespace is None:
        return _message_for_unresolved_user()
    store = get_store()
    existing = await store.aget(namespace, memory_id)
    if existing is None:
        return f"Nenhuma memória encontrada com id '{memory_id}'."
    await store.adelete(namespace, memory_id)
    return f"Memória '{memory_id}' removida."
