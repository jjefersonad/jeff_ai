from dotenv import load_dotenv
from pathlib import Path
from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend, CompositeBackend, StateBackend, StoreBackend

from src.models.ollama_model import ollama_model
from src.agents.subagents.fullstack import fullstack_subagent
from src.tools.technical_spec_tools import merge_generated_files
from src.tools.deep_agent_tools import get_date_time_current

# Carrega variáveis do arquivo .env
load_dotenv()

# Configurações de diretórios
PATH_DIR = Path(__file__).parent.parent.parent
SKILLS_DIR = PATH_DIR.resolve() / "skills/"
OUTPUTS_DIR = PATH_DIR.resolve() / "outputs/"

# O LangGraph API vai gerenciar a persistência automaticamente.
# Não instancie nem passe o PostgresSaver manualmente aqui.
agent = create_deep_agent(
    model=ollama_model,
    subagents=[fullstack_subagent],
    tools=[merge_generated_files, get_date_time_current],
    system_prompt=f"""
Você é um agente ORQUESTRADOR.

Sua função:
- Use memória persistente via Postgres
- Entender o objetivo do usuário
- Decompor em sessões de documento de requisitos
- Criar um plano organizado usando write_todos
- Delegar cada sessão para o subagent usando task()
- Validar entregas
- Informação importante: ao criar o arquivo consolidado final deve preencher com a data atual para isso use a ferramenta 'get_date_time_current'
- Ao final, use OBRIGATORIAMENTE a ferramenta 'merge_generated_files' para unificar os arquivos gerados, na ordem.
- O arquivo consolidado deve ser salvo obrigatoriamente dentro do diretório '{OUTPUTS_DIR}' 
  (exemplo: '{OUTPUTS_DIR}/documento_final.md').
- Use ferramentas de escrita de arquivo disponíveis para persistir o resultado no diretório '{OUTPUTS_DIR}'.


Você NUNCA implementa código diretamente.

Sempre:
1. Analise o pedido do usuário
2. Use write_todos para criar tarefas (cada sessão do documento é uma tarefa)
3. Delegue cada tarefa usando task(name="fullstack_subagent", task="...")
4. Consolide os resultados

Os arquivos devem ser salvos em: {OUTPUTS_DIR}
""",
    skills=["/skills/"],
    backend=lambda rt: CompositeBackend(
        default=StateBackend(rt),
        routes={
            # outputs físicos
            f"{OUTPUTS_DIR}": FilesystemBackend(
                root_dir=OUTPUTS_DIR, virtual_mode=True
            ),

            # skills físicas
            "/skills/": FilesystemBackend(
                root_dir=SKILLS_DIR
            ),

            # memórias no postgres/store runtime
            "/memories/": StoreBackend(rt),
        },
    ),
)

agent = agent.with_config({"recursion_limit": 1000})
