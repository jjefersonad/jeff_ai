VALIDATION_SUBAGENT_PROMPT = """
Responda APENAS em JSON:

{
  "issues": ["string"],
  "security_risks": ["string"],
  "performance_risks": ["string"],
  "score": number
}

Máximo 300 palavras.
"""

validation_subagent = {
    "name": "validation_subagent",
    "description": "Valida o design do sistema e retorna issues, riscos e pontuação",
    "system_prompt": VALIDATION_SUBAGENT_PROMPT,
}