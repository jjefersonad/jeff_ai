"""Ponto único de exposição dos grafos LangGraph do Jeff AI.

Os `graph_id` expostos aqui — `agent`, `sdd_agent`, `assistant` — são os
referenciados por `langgraph.json`, `server.py` e `main.py`. A injeção de adapters
nos casos de uso vive em `composition/dependencies.py`.

A construção de cada grafo (`create_deep_agent`, subagentes e system prompts)
permanece nos módulos `src.agents.*`, que também pertencem à composição; este
módulo os agrega num único entrypoint canônico.
"""
from src.agents.assistant.agent import assistant
from src.agents.requirements_specialist import agent
from src.agents.sdd.orchestrator import sdd_agent

__all__ = ["agent", "assistant", "sdd_agent"]
