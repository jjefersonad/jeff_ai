"""Regressão: singleton do scheduler sobrevive ao loader de `webapp.py` do
`langgraph_api` (achado empírico 2026-07-28).

`langgraph_api.api.load_custom_app` monta `webapp.py` via
`importlib.util.spec_from_file_location("user_router_module", path)` — um
nome de módulo SINTÉTICO, desconectado de
`sys.modules["src.infrastructure.web.webapp"]`. Antes desta correção,
`composition/dependencies.py` importava o scheduler via
`from src.infrastructure.web.webapp import _task_scheduler` — um import
NORMAL (dotted path), que reexecuta `webapp.py` do zero (Python não sabe que
já existe um módulo equivalente sob o nome sintético) e cria uma SEGUNDA
instância de `_task_scheduler`, nunca iniciada pelo `_lifespan` real. Efeito
observado em produção: `create_scheduled_task` persistia a tarefa
corretamente, mas o job ficava "Adding job tentatively -- it will be
properly scheduled when the scheduler starts" para sempre — nunca disparava.

A correção move o singleton para `scheduler_instance.py`, um módulo que
NINGUÉM carrega via `spec_from_file_location` (só `webapp.py` é, por ser o
`http.app` do `langgraph.json`) — por isso qualquer import normal, de
qualquer lugar, sempre resolve para a mesma entrada em `sys.modules`.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_WEBAPP_PATH = str(
    Path(__file__).parent.parent / "src" / "infrastructure" / "web" / "webapp.py"
)


def _load_webapp_via_file_path_like_langgraph_api():
    """Replica `langgraph_api.api.load_custom_app` para `webapp.py`.

    Mesma API usada pelo `langgraph_api` real: `spec_from_file_location` +
    `module_from_spec` + `exec_module`, sob um nome sintético não relacionado
    ao path pontilhado do pacote.
    """
    spec = importlib.util.spec_from_file_location(
        "user_router_module_test", _WEBAPP_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_scheduler_instance_is_the_same_regardless_of_import_path() -> None:
    """A instância real do scheduler DEVE ser a mesma tanto para quem monta
    `webapp.py` (via file-path loader, como o `langgraph_api` faz) quanto
    para quem faz um import normal (como `composition/dependencies.py` faz)
    para agendar/cancelar uma tarefa."""
    from src.infrastructure.scheduling.scheduler_instance import (
        task_scheduler as normal_import_scheduler,
    )

    file_path_module = _load_webapp_via_file_path_like_langgraph_api()

    assert file_path_module.task_scheduler is normal_import_scheduler


def test_webapp_module_does_not_define_its_own_scheduler_instance() -> None:
    """Trava o bug: `webapp.py` NÃO PODE voltar a instanciar seu próprio
    `APSchedulerTaskScheduler()` diretamente — precisa sempre importar o
    singleton de `scheduler_instance.py`. Reintroduzir a instanciação aqui
    quebra o compartilhamento com quem chega via import normal."""
    src = Path(_WEBAPP_PATH).read_text()
    assert "APSchedulerTaskScheduler()" not in src, (
        "webapp.py não pode instanciar APSchedulerTaskScheduler() diretamente "
        "— importe `task_scheduler` de "
        "src.infrastructure.scheduling.scheduler_instance"
    )
