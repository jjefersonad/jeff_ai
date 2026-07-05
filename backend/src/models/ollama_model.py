import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

# Carrega variáveis do arquivo .env
load_dotenv()

# Model configuration
ollama_model = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "deepseek-v4-pro:cloud"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0.0,
    num_ctx=8192,
    timeout=180,  # 180 segundos (excede o timeout do Cloudflare de 120s)
)