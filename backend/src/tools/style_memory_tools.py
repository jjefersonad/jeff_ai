"""Ferramentas de memória de ESTILOS de design de imagem (por thread).

Persistem o design plan aprovado no Store do LangGraph (Postgres), permitindo:
- Reutilização de estilo ("na mesma vibe", "mantenha o estilo").
- Versionamento: cada save cria uma nova versão, sem sobrescrever as anteriores.
- Transferência explícita de estilo entre threads (parâmetro `thread_id`).

Namespace: ("styles", <thread_id>). Diferente de `memory_tools` (namespace global
`("memories",)`), aqui o estilo é associado ao thread da conversa. A leitura é por
recência (não semântica), então os itens NÃO precisam do campo `content`/embeddings.
"""
import datetime
import uuid

from langchain_core.tools import tool
from langgraph.config import get_config, get_store

STYLES_ROOT = "styles"


def _current_thread_id() -> str:
    """thread_id do runtime atual (via get_config), com fallback seguro."""
    config = get_config().get("configurable", {})
    return config.get("thread_id", "default_thread")


def _namespace(thread_id: str) -> tuple[str, str]:
    return (STYLES_ROOT, thread_id)


@tool
async def save_design_style(design_plan: str, final_prompt: str = "") -> str:
    """Salva um design plan APROVADO como uma NOVA versão de estilo do thread atual.

    Chame SOMENTE após o usuário aprovar o plano e a imagem ter sido gerada.
    Cada chamada cria uma nova versão (nunca sobrescreve as anteriores), preservando
    o histórico e permitindo reutilizar estilos depois com 'na mesma vibe'.
    Planos rejeitados NÃO devem ser salvos por esta ferramenta.
    """
    store = get_store()
    thread_id = _current_thread_id()
    created_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    key = f"{created_at}-{uuid.uuid4().hex[:8]}"
    await store.aput(
        _namespace(thread_id),
        key,
        {
            "design_plan": design_plan,
            "final_prompt": final_prompt,
            "created_at": created_at,
        },
    )
    return f"Estilo salvo (versão {key}) para o thread {thread_id}."


@tool
async def load_design_style(thread_id: str = "") -> str:
    """Recupera o estilo (design plan) MAIS RECENTE de um thread.

    Use quando o usuário pedir 'na mesma vibe', 'mantenha o estilo', ou referir-se a
    um estilo anterior. Para transferir o estilo de OUTRA conversa, informe o
    `thread_id` de origem; sem ele, usa o thread atual.
    """
    store = get_store()
    target = thread_id or _current_thread_id()
    items = await store.asearch(_namespace(target), limit=100)
    if not items:
        return f"Nenhum estilo salvo para o thread {target}."
    latest = max(items, key=lambda it: it.value.get("created_at", ""))
    value = latest.value
    return (
        f"Estilo mais recente (thread {target}, versão {latest.key}):\n"
        f"Design plan:\n{value.get('design_plan', '')}\n\n"
        f"Prompt final: {value.get('final_prompt', '')}"
    )


@tool
async def list_design_styles(thread_id: str = "") -> str:
    """Lista as versões de estilo salvas para um thread (mais recentes primeiro)."""
    store = get_store()
    target = thread_id or _current_thread_id()
    items = await store.asearch(_namespace(target), limit=100)
    if not items:
        return f"Nenhum estilo salvo para o thread {target}."
    ordered = sorted(
        items, key=lambda it: it.value.get("created_at", ""), reverse=True
    )
    lines = []
    for item in ordered:
        created = item.value.get("created_at", "?")
        first_line = (item.value.get("design_plan", "") or "").strip().splitlines()
        summary = first_line[0][:80] if first_line else ""
        lines.append(f"- {created} (v {item.key}): {summary}")
    return "\n".join(lines)
