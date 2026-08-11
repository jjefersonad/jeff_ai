"""Domínio de email: entidade `EmailAccount`.

PURO: zero import de framework. `EmailAccount` guarda metadata de baixa
sensibilidade e alta frequência de escrita (status, `last_synced_at`) —
os segredos (host/porta/usuário/senha IMAP e SMTP) vivem numa entrada
`UserIntegration` separada (`integration_type="imap"`), referenciada por
`user_integration_id` (design Decision 1 de `email-client-imap-mvp`: evita
recifrar segredos a cada heartbeat de sync).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum

from src.domain.shared.errors import DomainError


class EmailAccountStatus(str, Enum):
    """Status de sincronização de uma conta de email (REQ-003 email-account-management)."""

    CONNECTED = "connected"
    ERROR = "error"
    SYNCING = "syncing"


@dataclass
class EmailAccount:
    """Uma conta de email genérica IMAP/SMTP pertencente a um único `user_id`.

    `user_integration_id` referencia a entrada `UserIntegration`
    (`integration_type="imap"`) que guarda as credenciais cifradas —
    nunca duplicadas aqui.
    """

    id: str
    user_id: str
    user_integration_id: str
    display_name: str
    provider: str = "imap"
    status: EmailAccountStatus = EmailAccountStatus.CONNECTED
    last_synced_at: datetime | None = None
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        """Valida que os campos identificadores obrigatórios não estão vazios."""
        for attr_name in ("id", "user_id", "user_integration_id", "display_name"):
            value = getattr(self, attr_name)
            if not isinstance(value, str) or not value.strip():
                raise DomainError(
                    f"EmailAccount.{attr_name} é obrigatório e não pode ser vazio."
                )


@dataclass
class Email:
    """Uma mensagem de email persistida na tabela `emails`.

    Todos os campos vindo da tabela — `to_addresses`, `cc_addresses` e
    `bcc_addresses` são JSONB em Postgres e serializados como `list[str]`.
    `body_html` é sanitizado no ingest pelo sync worker, nunca na leitura.
    Pertence a um `email_account_id` que, via `email_accounts.user_id`,
    é escopado ao `user_id` dono.
    """

    id: str
    email_account_id: str
    message_id: str
    thread_id: str | None
    folder: str
    from_address: str
    from_name: str | None
    to_addresses: list[str]
    cc_addresses: list[str]
    bcc_addresses: list[str]
    subject: str | None
    body_html: str | None
    body_text: str | None
    is_read: bool
    is_starred: bool
    has_attachments: bool
    contact_id: str | None
    received_at: datetime
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class ParsedMessage:
    """Uma mensagem IMAP já parseada, com `body_html` sanitizado.

    Produzida por `fetch_new_messages` (`src/infrastructure/email/imap_client.py`)
    a partir dos bytes RFC822 brutos — nunca carrega HTML não sanitizado
    (design Decision 3 de `email-client-imap-mvp`: sanitização acontece no
    ingest, não só na renderização).
    """

    uid: str
    message_id: str
    folder: str
    from_address: str
    from_name: str | None
    to_addresses: list[str]
    subject: str | None
    body_html: str | None
    body_text: str | None
    received_at: datetime


@dataclass
class ParsedAttachment:
    """Metadata de um anexo já extraído para armazenamento, pronto para persistir.

    Consumida por `EmailRepositoryPort.upsert_email` — a extração dos bytes
    brutos e a escolha de `storage_path` são responsabilidade de quem chama
    (o sync worker), não deste tipo.
    """

    filename: str
    mime_type: str | None
    size_bytes: int | None
    storage_path: str
