# ⚠️ LEGADO — NÃO USE

Estes scripts (`pack.py`, `unpack.py`, `soffice.py`, `validate.py`,
`recalc.py` em `../`, `helpers/*`, `validators/*`, `schemas/*`) eram o
caminho original de geração/edição de `.xlsx` baseado em
**soffice/LibreOffice/pandoc**. Foram **aposentados** pela change
`custom-office-doc-tools` porque dependiam de binários externos frágeis.

## Use a tool nativa

Para **criar** um `.xlsx` novo, use a tool registrada no `assistant` e no
`requirements_specialist`:

```python
result = await create_xlsx_spreadsheet.coroutine(XlsxDocumentInput(...))
```

A tool usa `openpyxl`, não precisa de binários externos, e devolve
`{path, url, metadata}`. Veja `../SKILL.md` para detalhes.

## Edição de arquivos existentes / recálculo de fórmulas

**Fora do escopo** desta entrega. `recalc.py` (que invocava soffice para
forçar o recálculo) foi aposentado: a string da fórmula já é gravada pelo
openpyxl, e o viewer (Excel/Sheets) calcula ao abrir.

## Manutenção

Estes arquivos ficam aqui apenas para referência histórica. Não há planos
de removê-los definitivamente neste ciclo, mas o código de runtime do
projeto **não deve invocá-los**.
