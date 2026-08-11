"""Domínio de email — entidade `EmailAccount`.

PURO: zero import de framework. Persistência e HTTP ficam em
`infrastructure/`; validação de `config` IMAP/SMTP fica em
`src/application/integrations/config_schemas.py`.
"""
from src.domain.email.models import (
    Email,
    EmailAccount,
    EmailAccountStatus,
    ParsedAttachment,
    ParsedMessage,
)

__all__ = [
    "Email",
    "EmailAccount",
    "EmailAccountStatus",
    "ParsedAttachment",
    "ParsedMessage",
]
