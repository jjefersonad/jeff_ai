"""Cliente IMAP: login, sincronização de mensagens e sanitização de HTML.

`verify_imap_login` (email-client-imap-mvp-task-accounts-2) distingue duas
famílias de falha, propositalmente:

- Credenciais recusadas pelo servidor (`login()` retorna `NO`/`BAD`) → levanta
  `ImapAuthError`, um tipo próprio, nunca derivado de `OSError`/`TimeoutError`.
- Falha de rede/DNS/timeout ao conectar (`wait_hello_from_server`) → propaga a
  exceção original do `aioimaplib`/`asyncio` sem embrulhar, para que o
  chamador (REQ-003 do spec `email-account-management`, usado pelo sync
  worker) consiga diferenciar "credencial errada" de "servidor fora do ar
  agora" sem inspecionar mensagens de erro.

Nunca inclui a senha em texto puro em nenhuma mensagem de exceção — o
resultado do `login()` (`OK`/`NO`/`BAD`) não carrega a senha, e o próprio
`aioimaplib` já faz `scrub` da senha nos logs internos do comando LOGIN.

`fetch_new_messages`/`sanitize_body_html` (email-client-imap-mvp-task-sync-1):
busca mensagens com UID acima de um watermark por pasta (REQ-005
`email-account-management`) e sanitiza `body_html` com `nh3` antes de
devolver os dados parseados — nunca persiste HTML não sanitizado (REQ-002
`email-inbox`, design Decision 3).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from email import message_from_bytes, policy
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

import aioimaplib
import nh3

from src.application.integrations.config_schemas import (
    GmailIntegrationConfig,
    ImapIntegrationConfig,
)
from src.domain.email.models import ParsedMessage

_FETCH_LINE_RE = re.compile(rb"^\d+ FETCH \(")


class ImapAuthError(Exception):
    """Servidor IMAP recusou o login (`NO`/`BAD`) — credenciais inválidas."""


async def verify_imap_login(config: ImapIntegrationConfig) -> None:
    """Tenta autenticar no servidor IMAP de `config`; não retorna nada em sucesso.

    Raises:
        ImapAuthError: login recusado pelo servidor.
        Exception: qualquer falha de conexão/rede/timeout propaga sem
            alteração (ver docstring do módulo).
    """
    client = aioimaplib.IMAP4_SSL(host=config.imap_host, port=config.imap_port)
    await client.wait_hello_from_server()
    try:
        response = await client.login(config.imap_username, config.imap_password)
        if response.result != "OK":
            raise ImapAuthError(
                f"Login IMAP recusado pelo servidor (result={response.result!r})."
            )
    finally:
        await client.logout()


async def _authenticate(
    client: aioimaplib.IMAP4_SSL, config: ImapIntegrationConfig | GmailIntegrationConfig
) -> None:
    """Autentica `client` — XOAUTH2 para contas Gmail, LOGIN para as demais.

    `aioimaplib` já suporta XOAUTH2 nativamente (`IMAP4.xoauth2`), então não
    é preciso montar a string SASL na mão (design Decision 1 de
    `gmail-account-oauth-connection`).
    """
    if isinstance(config, GmailIntegrationConfig):
        # `IMAP4ClientProtocol.xoauth2` tipa `token: str` e monta o SASL com
        # `f"...{token}...".encode("ascii")`. Passar `bytes` (via `.encode()`)
        # corrompe o Bearer no f-string (`b'ya29...'`) — o Gmail não responde
        # OK e o `wait_for(..., timeout=10)` vira `TimeoutError`, marcando a
        # conta como `error` no sync worker (produção 2026-08-12).
        # O wrapper `IMAP4.xoauth2` tipa `token: bytes`, mas só repassa ao
        # protocolo; o tipo efetivo exigido é `str`.
        await client.xoauth2(config.imap_username, config.access_token)
    else:
        await client.login(config.imap_username, config.imap_password)


def sanitize_body_html(raw_html: str) -> str:
    """Remove tags/atributos perigosos (`<script>`, `onclick`, ...) de HTML de email.

    Chamada no ingest (`_parse_message`), antes de qualquer persistência —
    nunca só na renderização (design Decision 3).
    """
    return nh3.clean(raw_html)


#: Teto por poll — evita que um catch-up de milhares de UIDs trave o
#: worker por horas (e atrase o mail novo). Polls seguintes continuam
#: de onde o watermark parou.
_FETCH_BATCH_SIZE = 50

#: No primeiro sync (`watermark == 0`), não reprocessa o histórico
#: inteiro da caixa: só as N mensagens mais recentes. Caixas Gmail
#: típicas têm milhares de UIDs; baixar tudo um-a-um bloqueia o poll
#: e o `EXISTS` de mail novo fica só como log ignorado do aioimaplib.
_INITIAL_SYNC_LIMIT = 100


async def fetch_new_messages(
    config: ImapIntegrationConfig | GmailIntegrationConfig, folder: str, watermark: int
) -> list[ParsedMessage]:
    """Busca mensagens de `folder` com UID acima de `watermark`.

    `watermark` é o maior UID já sincronizado para essa pasta; a busca usa
    `UID SEARCH {watermark + 1}:*` (via `client.uid_search(...)` — o
    `client.uid("search", ...)` da `aioimaplib` só aceita FETCH/STORE/
    COPY/MOVE/EXPUNGE e levanta `Abort` em SEARCH; o wrapper
    `IMAP4.search(..., by_uid=...)` não expõe `by_uid` no client de alto
    nível, só no `IMAP4ClientProtocol`, então `uid_search` é a API
    documentada), então o próprio servidor filtra o que é novo.

    Autentica via `_authenticate` — XOAUTH2 para `GmailIntegrationConfig`,
    LOGIN para `ImapIntegrationConfig` (gmail-account-oauth-connection).

    Limita o lote: no primeiro sync (`watermark == 0`) fica com as
    `_INITIAL_SYNC_LIMIT` mais recentes; nos polls seguintes processa no
    máximo `_FETCH_BATCH_SIZE` UIDs (os mais antigos pendentes), para o
    watermark avançar sem monopolizar o worker.
    """
    # Timeout > default (10s): XOAUTH2 + SELECT em Gmail ocasionalmente
    # passam de 10s sob carga; o worker então marcava a conta `error`.
    client = aioimaplib.IMAP4_SSL(
        host=config.imap_host, port=config.imap_port, timeout=30.0
    )
    await client.wait_hello_from_server()
    try:
        await _authenticate(client, config)
        await client.select(folder)
        search_response = await client.uid_search(f"UID {watermark + 1}:*")
        uids = sorted(_extract_search_uids(search_response.lines))
        uids = _limit_uids_for_poll(uids, watermark=watermark)

        messages = []
        for uid in uids:
            fetch_response = await client.uid("fetch", str(uid), "(RFC822)")
            raw = _extract_rfc822_bytes(fetch_response.lines)
            messages.append(_parse_message(uid, folder, raw))
        return messages
    finally:
        await client.logout()


def _limit_uids_for_poll(uids: list[int], *, watermark: int) -> list[int]:
    """Recorta a lista de UIDs ao lote do poll (ver `_FETCH_BATCH_SIZE`)."""
    if not uids:
        return uids
    if watermark == 0 and len(uids) > _INITIAL_SYNC_LIMIT:
        # Mais recentes — inbox fica utilizável; histórico antigo fica de fora.
        return uids[-_INITIAL_SYNC_LIMIT:]
    if len(uids) > _FETCH_BATCH_SIZE:
        # Catch-up contínuo: mais antigos primeiro, watermark sobe monotônico.
        return uids[:_FETCH_BATCH_SIZE]
    return uids


def _extract_rfc822_bytes(lines: list[bytes]) -> bytes:
    for index, line in enumerate(lines):
        if isinstance(line, bytes) and _FETCH_LINE_RE.match(line):
            return lines[index + 1]
    raise ValueError("Resposta FETCH sem payload RFC822.")


def _extract_search_uids(lines: list[bytes]) -> list[int]:
    """Extrai os UIDs da resposta de `UID SEARCH`.

    O `aioimaplib` devolve `Response.lines` com o prefixo `* ` já removido,
    mas a keyword do comando (no caso `SEARCH`) permanece como primeiro
    token da linha (`b"SEARCH 101 102 103"`, não `b"101 102 103"`). Bug
    real encontrado em produção (2026-08-10): `int(b"SEARCH")` levantava
    `ValueError`, que era engolido pelo `except Exception` do sync worker e
    marcava a conta como `error` em vez de persistir as mensagens. Aqui
    pulamos tokens não-numéricos (a keyword) e juntamos todas as linhas —
    servidores que retornam muitos UIDs podem quebrar a resposta em mais
    de uma linha untagged.
    """
    uids: list[int] = []
    for line in lines:
        if not isinstance(line, (bytes, str)):
            continue
        tokens = line.split() if isinstance(line, bytes) else line.encode().split()
        for token in tokens:
            try:
                uids.append(int(token))
            except ValueError:
                # Provavelmente a keyword do comando (`SEARCH`); pula.
                continue
    return uids


def _parse_message(uid: int, folder: str, raw: bytes) -> ParsedMessage:
    parsed = message_from_bytes(raw, policy=policy.default)

    from_name, from_address = parseaddr(parsed.get("From", ""))
    to_addresses = [address for _, address in getaddresses([parsed.get("To", "")])]

    body_html: str | None = None
    body_text: str | None = None
    if parsed.is_multipart():
        for part in parsed.walk():
            content_type = part.get_content_type()
            if content_type == "text/html" and body_html is None:
                body_html = part.get_content()
            elif content_type == "text/plain" and body_text is None:
                body_text = part.get_content()
    elif parsed.get_content_type() == "text/html":
        body_html = parsed.get_content()
    else:
        body_text = parsed.get_content()

    date_header = parsed.get("Date")
    received_at = parsedate_to_datetime(date_header) if date_header else datetime.now(UTC)

    return ParsedMessage(
        uid=str(uid),
        message_id=(parsed.get("Message-ID") or str(uid)).strip("<>"),
        folder=folder,
        from_address=from_address,
        from_name=from_name or None,
        to_addresses=to_addresses,
        subject=parsed.get("Subject"),
        body_html=sanitize_body_html(body_html) if body_html else None,
        body_text=body_text.strip() if body_text else None,
        received_at=received_at,
    )
