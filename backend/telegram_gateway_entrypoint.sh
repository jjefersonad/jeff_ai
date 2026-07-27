#!/bin/sh
# Wrapper entrypoint para o `telegram_gateway`.
# Necessário porque o `sh -c "..."` inline no docker-compose (e qualquer
# `sh` rodado sem tty) abre stdout/stderr como pipes que ficam sem leitor
# após o `exec python`, fazendo o `python` travar no write quando o buffer
# enche. Sintoma: `docker logs` mostra `pip install` mas nada do `python`.
# O processo fica vivo (em `ep_poll` no asyncio loop) mas invisível.
#
# Esse script:
# 1. Faz `pip install` do `python-telegram-bot`.
# 2. **Reabre** FD 1/2 a partir de `/proc/1/fd/1` e `/proc/1/fd/2` (que o
#    Docker aponta para o TTY do container, não para um pipe). Isso quebra
#    a herança do pipe problemático.
# 3. `exec python -u` substituindo o `sh` mas mantendo os FDs novos.
set -eu

echo "[telegram_gateway] instalando python-telegram-bot..."
pip install --no-cache-dir 'python-telegram-bot>=21.0' >&2
echo "[telegram_gateway] pip install ok, iniciando gateway..." >&2

# Reabrir stdout/stderr a partir do TTY do container (não dos pipes do sh).
# FD 0 do container é /dev/null; FD 1/2 são pipes do docker -> TTY.
exec </dev/null
exec 1>/proc/1/fd/1 2>/proc/1/fd/2
exec python -u src/infrastructure/telegram/telegram_gateway.py

