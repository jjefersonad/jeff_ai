"""Domínio de integrações de usuário — entidade `UserIntegration`.

PURO: zero import de framework. Persistência (cifra incluída) fica em
`infrastructure/`; validação de `config` por `integration_type` fica na
fronteira do caso de uso (`src/application/integrations/`).
"""
from src.domain.integrations.telegram_link_code import TelegramLinkCode
from src.domain.integrations.user_integration import UserIntegration
from src.domain.integrations.whatsapp_link_code import WhatsAppLinkCode

__all__ = ["TelegramLinkCode", "UserIntegration", "WhatsAppLinkCode"]
