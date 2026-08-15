# ⚠️ LEGADO — NÃO USE

Estes scripts (`pack.py`, `unpack.py`, `soffice.py`, `validate.py`, `helpers/*`,
`validators/*`, `schemas/*`) eram o caminho original de geração/edição de
`.docx` baseado em **pandoc/soffice/LibreOffice/docx-js**. Eles foram
**aposentados** pela change `custom-office-doc-tools` porque dependiam de
binários externos frágeis no ambiente do projeto.

## Use a tool nativa

Para **criar** um `.docx` novo, use a tool registrada no `assistant` e no
`requirements_specialist`:

```python
result = await create_docx_document.coroutine(DocxDocumentInput(...))
```

A tool usa `python-docx`, não precisa de binários externos, e devolve
`{path, url, metadata}`. Veja `../SKILL.md` para detalhes.

## Edição de arquivos existentes

**Fora do escopo** desta entrega. Se aparecer essa demanda, abra um follow-up
e reavalie se vale reintroduzir o caminho de manipulação XML.

## Manutenção

Estes arquivos ficam aqui apenas para referência histórica. Não há planos
de removê-los definitivamente neste ciclo, mas o código de runtime do
projeto **não deve invocá-los** — o lint de imports e os testes do projeto
não os cobrem.
