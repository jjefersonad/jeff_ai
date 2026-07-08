"""Camada de COMPOSIÇÃO — frameworks & drivers (a mais externa).

Responsabilidade: montar o sistema. Aqui ficam a construção dos grafos LangGraph
(`create_deep_agent`), os subagentes, o `backend_factory`/`CompositeBackend` e a
injeção (fiação manual) dos adapters de infraestrutura nos casos de uso. É o
único lugar que conhece todas as camadas ao mesmo tempo.

Regra da Dependência: pode importar de qualquer camada interna; nada interno
importa de `composition`. Os entrypoints (`langgraph.json`, `server.py`,
`entrypoint.sh`, `main.py`) apontam para os grafos expostos aqui, preservando os
`graph_id` (`agent`, `sdd_agent`, `assistant`).
"""
