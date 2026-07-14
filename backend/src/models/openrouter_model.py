"""OpenRouter chat model — usado como fallback quando o Ollama Cloud falha.

`openrouter/free` é o router gratuito da OpenRouter: seleciona automaticamente
entre os modelos free-tier que suportam tool calling, o que é obrigatório
neste projeto (deepagents chama `bind_tools` em toda requisição). Ver
`fallback_model.py` para a composição com o `ollama_model` primário.
"""

import os

from dotenv import load_dotenv
from langchain_openrouter import ChatOpenRouter

load_dotenv()

openrouter_model = ChatOpenRouter(
    model=os.getenv("OPENROUTER_MODEL", "openrouter/free"),
    api_key=os.getenv("OPENROUTER_API_KEY"),
    temperature=0.0,
    # `timeout` é em MILISSEGUNDOS aqui (diferente do `ChatOllama`, que é em
    # segundos) — 30_000 = 30s por tentativa HTTP.
    timeout=30_000,
    # `max_retries=0` NÃO significa "sem retry": pula o `RetryConfig` do
    # `langchain-openrouter` e cai no default do SDK `openrouter`, que
    # verificamos na prática retentar por bem mais de 2 minutos em 429 antes
    # de desistir — inaceitável para um fallback que precisa ser rápido.
    # `max_retries=1` ativa o `RetryConfig` próprio do wrapper
    # (`max_elapsed_time = max_retries * 150_000` ms ≈ 150s no pior caso),
    # o que já é bem mais previsível.
    max_retries=1,
    app_url=os.getenv("OPENROUTER_APP_URL", "http://localhost:3000"),
    app_title=os.getenv("OPENROUTER_APP_TITLE", "Jeff AI"),
)
