# ⚠️ LEGADO — NÃO USE

Estes scripts (`pack.py`, `unpack.py`, `soffice.py`, `validate.py`,
`clean.py`, `add_slide.py`, `thumbnail.py` em `../`, `helpers/*`,
`validators/*`, `schemas/*`) eram o caminho original de geração/edição
de `.pptx` baseado em **soffice/LibreOffice/pptxgenjs/markitdown**. Foram
**aposentados** pela change `custom-office-doc-tools` porque dependiam de
binários externos frágeis.

## Use a tool nativa

Para **criar** um `.pptx` novo, use a tool registrada no `assistant` e no
`requirements_specialist`:

```python
result = await create_pptx_presentation.coroutine(PptxDocumentInput(...))
```

A tool usa `python-pptx`, não precisa de binários externos, e devolve
`{path, url, metadata}`. Veja `../SKILL.md` para detalhes.

## Edição de arquivos existentes / conversão para imagem/PDF

**Fora do escopo** desta entrega. `thumbnail.py` (que dependia de
Pillow + LibreOffice) foi aposentado.

## Manutenção

Estes arquivos ficam aqui apenas para referência histórica. Não há planos
de removê-los definitivamente neste ciclo, mas o código de runtime do
projeto **não deve invocá-los**.
