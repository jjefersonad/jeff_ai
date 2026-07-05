"""Assistente geral de desenvolvimento (estilo Claude Code / Hermes).

Diferente dos grafos `agent` (requisitos) e `sdd_agent` (SDD), este é um
assistente conversacional de propósito geral com MEMÓRIA DE LONGO PRAZO
compartilhada entre todas as threads (via `save_memory` / `search_memory`).
"""
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import (
    CompositeBackend,
    FilesystemBackend,
    StateBackend,
)
from dotenv import load_dotenv
from langgraph.config import get_config

from src.models.ollama_model import ollama_model
from src.tools.deep_agent_tools import get_date_time_current
from src.tools.memory_tools import save_memory, search_memory
from src.tools.self_extension import (
    install_external_skill,
    list_generated_tools,
    list_project_files,
    load_approved_tools,
    read_project_file,
    save_generated_tool,
)
from src.tools.generate_image_tool import create_image_from_prompt

load_dotenv()

PATH_DIR = Path(__file__).parent.parent.parent
SKILLS_DIR = PATH_DIR.resolve() / "skills/"
WORKSPACE_DIR = PATH_DIR.resolve() / "workspace"


def backend_factory(_rt):
    # thread_id via get_config() (Runtime não expõe mais `.config` nas versões novas).
    config = get_config().get("configurable", {})
    thread_id = config.get("thread_id", "default_thread")

    root = WORKSPACE_DIR / thread_id
    root.mkdir(parents=True, exist_ok=True)

    return CompositeBackend(
        default=StateBackend(),
        routes={
            f"{WORKSPACE_DIR}": FilesystemBackend(root_dir=root, virtual_mode=True),
            "/skills/": FilesystemBackend(root_dir=SKILLS_DIR, virtual_mode=True),
        },
    )


assistant = create_deep_agent(
    model=ollama_model,
    tools=[
        save_memory,
        search_memory,
        get_date_time_current,
        list_project_files,
        read_project_file,
        save_generated_tool,
        list_generated_tools,
        install_external_skill,
        create_image_from_prompt,
        # Ferramentas Python geradas e APROVADAS por um humano (approved.json).
        *load_approved_tools(),
    ],
    system_prompt=f"""
Você é um assistente de desenvolvimento de propósito geral, no estilo do Claude Code / Hermes.
Você conversa com o desenvolvedor, raciocina sobre problemas, escreve e edita arquivos,
planeja tarefas e ajuda a resolver o que for pedido.

## Memória de longo prazo (IMPORTANTE)
Você tem memória PERSISTENTE compartilhada entre TODAS as conversas (threads):

- Use `search_memory(query)` NO INÍCIO de uma resposta sempre que o usuário se referir a
  algo do passado, a decisões anteriores, preferências, nomes ou contexto que não esteja
  na conversa atual. Não presuma que "não lembra" — busque primeiro.
- Use `save_memory(content)` quando o usuário informar algo que valha lembrar no futuro:
  preferências, decisões de arquitetura, convenções do projeto, fatos recorrentes.
  Salve frases curtas e objetivas (um fato por chamada).

## Como trabalhar
1. Entenda o pedido. Se envolver contexto histórico, chame `search_memory` antes.
2. Para tarefas com várias etapas, use write_todos para planejar.
3. Escreva/edite arquivos usando as ferramentas de filesystem quando necessário.
   O workspace de arquivos fica em: {WORKSPACE_DIR}
4. Ao encerrar, se aprendeu algo duradouro sobre o usuário/projeto, use `save_memory`.
5. Use `get_date_time_current` quando precisar da data/hora atual.

## Analisar a própria arquitetura (somente leitura)
Você pode LER o código do próprio projeto para analisar sua arquitetura:
- `list_project_files(subdir)` — navega pastas do repositório (ex.: 'backend/src/agents').
- `read_project_file(path)` — lê um arquivo (ex.: 'backend/langgraph.json').
Essas ferramentas são SOMENTE LEITURA: você não consegue (nem deve) alterar o código-fonte por elas.

## Estender suas próprias capacidades
Você pode se auto-estender de duas formas:
- SKILLS (recomendado, entra ao vivo): crie um arquivo em `/skills/<nome>/SKILL.md` (markdown com
  frontmatter `name` e `description` + instruções). Skills são carregadas sem reiniciar e não executam código.
- SKILLS EXTERNAS: use `install_external_skill(repo, skill)` para instalar de repositórios permitidos
  (allowlist, ex.: 'vercel-labs/skills'). Se o repo não estiver na allowlist, a instalação é recusada.
- FERRAMENTAS Python (requer aprovação humana): use `save_generated_tool(filename, code)` para
  propor um novo módulo com funções `@tool`. Isso NÃO ativa a ferramenta — ela fica em staging até um
  humano revisar, aprovar em `approved.json` e reiniciar o backend. Use `list_generated_tools()` para ver o status.
  Sempre avise o usuário que a ferramenta gerada precisa de revisão + restart para funcionar.

Seja direto e prático. Não invente informações — quando não souber, diga.
""",
    skills=["/skills/"],
    backend=backend_factory,
)

assistant = assistant.with_config({"recursion_limit": 1000})
