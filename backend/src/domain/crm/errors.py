"""Erros de domínio do CRM (sem dependência de framework)."""
from __future__ import annotations


class DuplicateFieldDefinitionError(Exception):
    """Já existe definição com o mesmo (user_id, entity, key)."""
