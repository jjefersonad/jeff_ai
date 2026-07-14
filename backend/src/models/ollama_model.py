import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

# Carrega variáveis do arquivo .env
load_dotenv()

# Model configuration
#
# num_ctx=8192 estourava: system prompt + schemas de tools medem ~65.000 chars
# (~13.900 tokens estimados, unified-agent-realignment task skills-3) — ~170%
# do orçamento antes de qualquer turno do usuário. 32768 dá margem.
ollama_model = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "deepseek-v4-pro:cloud"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0.0,
    num_ctx=int(os.getenv("OLLAMA_NUM_CTX", "32768")),
    timeout=180,  # 180 segundos (excede o timeout do Cloudflare de 120s)
)