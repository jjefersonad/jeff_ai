"""Singleton do processo do `APSchedulerTaskScheduler`.

Vive em módulo PRÓPRIO — não em `webapp.py` — por um motivo específico e não
óbvio: `webapp.py` é carregado pelo `langgraph_api` via
`importlib.util.spec_from_file_location("user_router_module", path)`
(ver `LANGGRAPH_HTTP` em `docker-compose.yml`/`langgraph.json`), que registra
o módulo sob o nome SINTÉTICO `"user_router_module"` em vez do path
pontilhado real `src.infrastructure.web.webapp` — desconectado de
`sys.modules["src.infrastructure.web.webapp"]`.

Qualquer import NORMAL de `src.infrastructure.web.webapp` (ex.: de dentro de
`composition/dependencies.py`, alcançado pelo import comum da árvore do
grafo `unified`) faz o Python executar o ARQUIVO DE NOVO sob o path
pontilhado — criando uma SEGUNDA instância do módulo `webapp.py`, com seu
próprio `_task_scheduler` que NUNCA é iniciado (só o `_lifespan` da
instância que o `langgraph_api` efetivamente monta chama `.start()`).

Achado empírico (2026-07-28): tarefas agendadas eram criadas e persistidas
corretamente, mas nunca disparavam — o log mostrava "Adding job tentatively
-- it will be properly scheduled when the scheduler starts" para sempre,
porque o job ia parar nessa segunda instância nunca iniciada.

Este módulo em si NUNCA é carregado via `spec_from_file_location` (só
`webapp.py` é, por ser o `http.app` do `langgraph.json`) — importado
normalmente por QUALQUER consumidor (`webapp.py` incluso), ele sempre
resolve para a mesma entrada em `sys.modules`, garantindo uma única
instância real do scheduler no processo.
"""
from __future__ import annotations

from src.infrastructure.scheduling.apscheduler_task_scheduler import (
    APSchedulerTaskScheduler,
)

task_scheduler = APSchedulerTaskScheduler()

__all__ = ["task_scheduler"]
