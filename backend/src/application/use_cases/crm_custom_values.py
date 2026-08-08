"""Validação e merge shallow de `custom_values` do CRM."""
from __future__ import annotations

import re
from typing import Any

from src.domain.crm import FieldDefinition, FieldType
from src.domain.shared.errors import DomainError

_KEY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def validate_field_key(key: str) -> str:
    """Normaliza e valida slug de chave de campo personalizado."""
    cleaned = key.strip() if key else ""
    if not _KEY_RE.fullmatch(cleaned):
        raise DomainError(
            "field key inválida: use slug minúsculo "
            "(ex.: segmento, ticket_medio)."
        )
    return cleaned


def validate_custom_values(
    *,
    definitions: list[FieldDefinition],
    existing: dict[str, Any],
    incoming: dict[str, Any] | None,
) -> dict[str, Any]:
    """Valida `incoming` contra definições e faz merge shallow com `existing`.

    - chaves omitidas em ``incoming`` permanecem
    - valor ``None`` remove a chave
    - chave sem definição → DomainError
    - tipo incompatível → DomainError
    """
    if incoming is None:
        return dict(existing)

    by_key = {d.key: d for d in definitions}
    merged = dict(existing)
    for key, value in incoming.items():
        definition = by_key.get(key)
        if definition is None:
            raise DomainError(
                f"custom_values.{key}: não há definição de campo para esta chave."
            )
        if value is None:
            merged.pop(key, None)
            continue
        merged[key] = _coerce_value(definition.field_type, key, value)
    return merged


def _coerce_value(field_type: FieldType, key: str, value: Any) -> Any:
    if field_type is FieldType.TEXT:
        if not isinstance(value, str):
            raise DomainError(
                f"custom_values.{key}: tipo incompatível (esperado text/string)."
            )
        return value
    if field_type is FieldType.BOOLEAN:
        if not isinstance(value, bool):
            raise DomainError(
                f"custom_values.{key}: tipo incompatível (esperado boolean)."
            )
        return value
    if field_type is FieldType.NUMBER:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DomainError(
                f"custom_values.{key}: tipo incompatível (esperado number)."
            )
        return value
    raise DomainError(f"custom_values.{key}: field_type desconhecido.")
