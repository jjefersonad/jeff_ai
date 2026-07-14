"""Pre-flight check: falha rápido se o Postgres de POSTGRES_URI não estiver de pé.

`langgraph dev` abre o pool do checkpointer/store assim que inicia; se o
Postgres ainda não estiver acessível nesse instante, o `psycopg_pool` espera
30s e falha com um traceback de baixo nível. Este script tenta conectar por
um orçamento bem menor e, se falhar, imprime uma mensagem acionável dizendo
o comando exato para subir o container. Ver `make dev`.
"""
import os
import sys
import time
from urllib.parse import urlsplit

import psycopg
from dotenv import load_dotenv

DEFAULT_TOTAL_TIMEOUT = 5.0
DEFAULT_CONNECT_TIMEOUT = 1.0
DEFAULT_POLL_INTERVAL = 0.5


def wait_for_postgres(
    uri: str,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
    connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
    poll_interval: float = DEFAULT_POLL_INTERVAL,
) -> bool:
    """Tenta conectar em `uri` até `total_timeout` segundos. Retorna se conectou."""
    deadline = time.monotonic() + total_timeout
    while True:
        try:
            with psycopg.connect(uri, connect_timeout=connect_timeout):
                return True
        except psycopg.OperationalError:
            if time.monotonic() >= deadline:
                return False
            time.sleep(poll_interval)


def main() -> int:
    """CLI: valida POSTGRES_URI e sai com 0/1 conforme a conectividade."""
    load_dotenv()
    uri = os.environ.get("POSTGRES_URI")
    if not uri:
        print(
            "ERRO: POSTGRES_URI não está definida (esperada em backend/.env).",
            file=sys.stderr,
        )
        return 1

    parsed = urlsplit(uri)
    host_port = f"{parsed.hostname}:{parsed.port}"

    if wait_for_postgres(uri):
        print(f"Postgres OK ({host_port}).")
        return 0

    print(
        f"ERRO: Postgres não está acessível em {host_port}.\n"
        "Suba o container primeiro: docker compose up -d jeff_ia_postgres jeff_ia_redis\n"
        "Se já estiver rodando, cheque os logs: docker compose logs jeff_ia_postgres",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
