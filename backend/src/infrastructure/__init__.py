"""Camada de INFRAESTRUTURA — adapters.

Responsabilidade: implementar os ports da camada de aplicação usando tecnologia
concreta — provedores de LLM (Ollama/Gemini), Postgres (checkpointer/store),
filesystem e busca web (Tavily). Converte tipos crus de framework/SDK em tipos
de domínio/aplicação na fronteira do port.

Regra da Dependência: pode importar de `domain` e `application` (para
implementar os ports), mas as camadas internas NUNCA importam daqui. A leitura
de env/segredos (`POSTGRES_URI`, `OLLAMA_BASE_URL`, `GOOGLE_API_KEY`,
`TAVILY_API_KEY`) ocorre nesta camada ou em `composition`.
"""
