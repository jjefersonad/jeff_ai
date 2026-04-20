import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama

# Carrega variáveis do arquivo .env
load_dotenv()

# Model configuration
ollama_model = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "minimax-m2.7:cloud"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0.0,
)