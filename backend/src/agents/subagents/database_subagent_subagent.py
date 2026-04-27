DATABASE_SUBAGENT_PROMPT = """
Responda APENAS em JSON:

{
  "entities": ["string"],
  "relationships": ["string"],
  "indexes": ["string"],
  "risks": ["string"]
}

Máximo 300 palavras. Sem explicações.
"""

database_subagent = {
    "name": "database_subagent",
    "description": "Cria esquemas de banco de dados e retorna JSON compacto",
    "system_prompt": DATABASE_SUBAGENT_PROMPT,
}