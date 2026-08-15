# Scripts legados — todos aposentados

A pasta `office/` e os arquivos soltos desta pasta (`accept_changes.py`,
`comment.py`, e o diretório `templates/`) eram o caminho original baseado em
**pandoc/soffice/LibreOffice/docx-js**. Foram aposentados pela change
`custom-office-doc-tools`.

Para gerar documentos Word, use a tool nativa (registrada em
`src/agents/assistant/agent.py` e `src/agents/requirements_specialist.py`):

- `create_docx_document` — `.docx` via python-docx

Detalhes em `../SKILL.md` e em `office/README.md`.
