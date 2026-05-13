from pathlib import Path
from deepagents import SubAgent
from src.tools.deep_agent_tools import ls, read_file, write_file

# Configurações de diretórios
PATH_DIR = Path(__file__).parent.parent.parent
OUTPUTS_DIR = PATH_DIR.resolve() / "outputs/"

fullstack_subagent = SubAgent(
    name="fullstack_subagent",
    description=f"Creates requirement document sections in {OUTPUTS_DIR}",
    system_prompt=f"""
Você é um escritor técnico especializado em criar documentos de requisitos.

Para cada tarefa:
1. Use ls para verificar o diretório {OUTPUTS_DIR}
2. Use write_file para criar o arquivo solicitado
3. Use read_file para verificar

Os arquivos devem ser salvos em: {OUTPUTS_DIR}
"""
)