from langchain_core.tools import tool
import os

@tool
def ls(path: str) -> str:
    """Lista arquivos de um diretório"""
    if not os.path.exists(path):
        return f"Diretório não encontrado: {path}"
    return "\n".join(os.listdir(path))

@tool
def read_file(path: str) -> str:
    """Lê o conteúdo de um arquivo. Retorna mensagem se não existir."""
    if not os.path.exists(path):
        return f"Arquivo não encontrado: {path}"
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

@tool
def write_file(path: str, content: str) -> str:
    """Escreve conteúdo em um arquivo."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Arquivo escrito em {path}"

@tool
def get_date_time_current() -> str:
    """Retorna a data e hora atual no formato DD/MM/YYYY."""
    from datetime import datetime
    return datetime.now().strftime("%d/%m/%Y %H:%M:%S")