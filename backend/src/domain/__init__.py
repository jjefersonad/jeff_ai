"""Camada de DOMÍNIO — o núcleo puro do Jeff AI.

Responsabilidade: entidades, value objects e domain services que expressam a
linguagem ubíqua do produto (RequirementDocument, ImageDesign, DesignStyle,
Feature, ...). Contém regra de negócio, nada mais.

Regra da Dependência (Clean Architecture): esta é a camada MAIS INTERNA.
NÃO pode importar de `application`, `infrastructure` nem `composition`, e NÃO
pode importar frameworks/I/O (`langgraph`, `deepagents`, `langchain_*`,
`psycopg`, `httpx`, acesso a filesystem/env). Se precisar de algo do mundo
externo, defina um port na camada de aplicação — o domínio nunca o conhece.

Enforçado automaticamente por import-linter (ver `pyproject.toml`).
"""
