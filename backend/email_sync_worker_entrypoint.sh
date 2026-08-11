#!/bin/sh
# Wrapper entrypoint para o `email_sync_worker`.
#
# Necessário pelo mesmo motivo do `telegram_gateway_entrypoint.sh`: o
# `sh -c "..."` inline do docker-compose abre stdout/stderr como pipes que
# ficam sem leitor após o `exec python`, fazendo o `python` travar no
# write quando o buffer enche. Sintoma: `docker logs` mostra nada do
# `python`. O processo fica vivo (asyncio loop) mas invisível.
#
# Esse script:
# 1. **Reabre** FD 1/2 a partir de `/proc/1/fd/1` e `/proc/1/fd/2` (que o
#    Docker aponta para o TTY do container). Quebra a herança do pipe.
# 2. `exec python -u` substituindo o `sh` mas mantendo os FDs novos.
#
# Diferente do `telegram_gateway_entrypoint.sh`: o email_sync_worker NÃO
# precisa de `pip install` extra — `aioimaplib` e `aiosmtplib` já vêm via
# `pyproject.toml`/Dockerfile.backend (deps do sync worker e do send path).
set -eu

echo "[email_sync_worker] iniciando worker..." >&2

# Reabrir stdout/stderr a partir do TTY do container (não dos pipes do sh).
exec </dev/null
exec 1>/proc/1/fd/1 2>/proc/1/fd/2

exec python -u src/infrastructure/email/email_sync_worker.py
