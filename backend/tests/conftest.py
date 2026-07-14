"""Configuração global de testes.

Desliga o tracing do LangSmith para a suíte inteira. `backend/.env` traz
`LANGCHAIN_TRACING_V2=true` (uso normal do assistente rodando de verdade),
mas testes que invocam o grafo (`graph.invoke(...)`) herdam isso e o
LangChain tenta exportar cada execução para a API do LangSmith em uma
thread de background.

Em ambientes sem rota de rede para `api.smith.langchain.com`, essa thread
nunca consegue drenar a fila de exportação — e a fila cresce sem limite a
cada teste que roda o grafo. Medido em produção: ~200MB antes do primeiro
teste que invoca o grafo, e >2.5GB poucos segundos depois, escalando até o
kernel matar o processo por OOM (~12.5GB de RSS).

Este módulo roda ANTES de qualquer teste ser importado (`conftest.py` na
raiz de `tests/` é carregado primeiro pelo pytest) — momento em que
`os.environ` ainda pode ser ajustado antes que qualquer código do
LangChain/LangSmith leia essas variáveis.
"""
import os

os.environ["LANGCHAIN_TRACING_V2"] = "false"
os.environ["LANGSMITH_TRACING"] = "false"
os.environ.pop("LANGSMITH_API_KEY", None)
os.environ.pop("LANGCHAIN_API_KEY", None)
