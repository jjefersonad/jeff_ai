# Scripts legados — todos aposentados

A pasta `office/` e os arquivos soltos desta pasta (`recalc.py` em xlsx,
`clean.py`/`add_slide.py`/`thumbnail.py` em pptx, `accept_changes.py`/`comment.py`
em docx) eram o caminho original baseado em **pandoc/soffice/LibreOffice**.
Foram aposentados pela change `custom-office-doc-tools`.

Para gerar documentos, use as tools nativas (registradas em
`src/agents/assistant/agent.py` e `src/agents/requirements_specialist.py`):

- `create_docx_document` — `.docx` via python-docx
- `create_xlsx_spreadsheet` — `.xlsx` via openpyxl
- `create_pptx_presentation` — `.pptx` via python-pptx

Detalhes em `../SKILL.md` (de cada skill) e em `office/README.md`.
