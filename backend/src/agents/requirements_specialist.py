"""Orquestrador de documentos de requisitos (Jeff AI).

Compõe o grafo `agent` do deepagents com tools de I/O, ferramentas nativas
de geração de documentos Office (.docx/.xlsx/.pptx) e dois subagentes:
`fullstack_subagent` (escrita técnica) e `image_design_subagent` (geração
visual com gate de aprovação).
"""
from pathlib import Path

from deepagents import create_deep_agent
from dotenv import load_dotenv

from src.agents.subagents.fullstack import fullstack_subagent
from src.agents.subagents.image_design import image_design_subagent
from src.composition.backends import FsRoute, make_backend_factory
from src.models.ollama_model import ollama_model
from src.tools.create_docx_document_tool import create_docx_document
from src.tools.create_pptx_presentation_tool import create_pptx_presentation
from src.tools.create_xlsx_spreadsheet_tool import create_xlsx_spreadsheet
from src.tools.deep_agent_tools import get_date_time_current
from src.tools.fetch_reference_image_tool import (
    check_reference_image,
    fetch_reference_image,
)
from src.tools.technical_spec_tools import merge_generated_files

# Carrega variáveis do arquivo .env
load_dotenv()

# Configurações de diretórios
PATH_DIR = Path(__file__).parent.parent.parent
SKILLS_DIR = PATH_DIR.resolve() / "skills/"
OUTPUTS_DIR = PATH_DIR.resolve() / "outputs/"

backend_factory = make_backend_factory(
    routes=[
        FsRoute(prefix=f"{OUTPUTS_DIR}", base_dir=OUTPUTS_DIR, per_thread=True),
        FsRoute(prefix="/skills/", base_dir=SKILLS_DIR),
    ],
    include_store=True,
)


# O LangGraph API vai gerenciar a persistência automaticamente.
# Não instancie nem passe o PostgresSaver manualmente aqui.
agent = create_deep_agent(
    model=ollama_model,
    subagents=[fullstack_subagent, image_design_subagent],
    tools=[
        merge_generated_files,
        get_date_time_current,
        fetch_reference_image,
        check_reference_image,
        # Geração nativa de documentos Office (.docx/.xlsx/.pptx). Sem
        # interrupt_on — geração direta, sem gate de aprovação.
        create_docx_document,
        create_xlsx_spreadsheet,
        create_pptx_presentation,
    ],
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

Geração de imagens:
- Quando o pedido envolver criar imagem, banner, ilustração ou design visual,
  delegue para o subagente de design usando task(name="image_design_subagent", task="...").
- O 'image_design_subagent' apresenta um plano de design e EXIGE aprovação explícita do
  usuário (via interrupt) ANTES de gerar a imagem. NUNCA gere imagens diretamente.

Geração de documentos Office (.docx/.xlsx/.pptx):
- Para entregar requisitos em formato Word/Excel/PowerPoint use as tools nativas
  diretamente: `create_docx_document`, `create_xlsx_spreadsheet`, `create_pptx_presentation`.
  Cada uma devolve `{{path, url, metadata}}` — apresente o link `url` ao usuário
  (ex.: [documento.docx](http://host:8080/api/files/docx/...)).
- NÃO há subagente nem gate de aprovação para documentos Office: a geração é
  direta e determinística.
- Crie apenas documentos novos (criação do zero). Edição de arquivos existentes
  está fora do escopo.

Os arquivos devem ser salvos em: {OUTPUTS_DIR}
""",
    skills=["/skills/"],
    backend=backend_factory
)

agent = agent.with_config({"recursion_limit": 1000})
