---
name: image-generation
description: Documenta o fluxo de geração de imagens do Jeff AI — o image_design_subagent (planejamento + geração imediata via create_image_from_prompt), a tool create_image_from_prompt (Union[str, ImageDesignInput] -> dict) e a memória de estilos por thread.
---

# Image Generation Skill

Geração de imagens no Jeff AI é feita por um **subagente de design** (`image_design_subagent`)
que planeja a imagem, apresenta o design plan e **gera imediatamente** via
`create_image_from_prompt` (Google Gemini). Não há gate HITL (`interrupt_on`) nem
botões aprovar/editar/rejeitar antes da geração.

## Arquitetura do fluxo

```
usuário → orquestrador (unified) ──► task(name="image_design_subagent")
                                        │  1. analisa contexto
                                        │  2. monta design plan (concept, paleta, estilo…)
                                        │  3. apresenta o plano (markdown)
                                        │  4. create_image_from_prompt (sem interrupt_on)
                                        ▼
                                 create_image_from_prompt → Gemini → PNG + sidecar JSON
                                        │
                                        ▼
                                 save_design_style (após sucesso)
```

- **Quem delega:** o orquestrador unificado registra o `image_design_subagent` e
  delega via `task(...)`. Outros subagentes/skills não chamam a tool de imagem
  diretamente — sempre deferem ao `image_design_subagent`.
- **Sem gate de aprovação:** `create_image_from_prompt` executa imediatamente.
  O subagente apresenta o plan e chama a tool na mesma resposta; NÃO pede
  confirmação em texto ("ok"/"sim"/"prossiga").

## Regra CRÍTICA — uma imagem por vez

NUNCA chame `create_image_from_prompt` mais de UMA vez na mesma resposta. Gere
exatamente UMA imagem por resposta. Se o usuário pedir várias imagens/variações,
gere a PRIMEIRA, aguarde o resultado, e só então proponha e gere as próximas.

## Tool `create_image_from_prompt`

Localização: `backend/src/tools/generate_image_tool.py`. Modelo: `gemini-3.1-flash-image`.

```python
@tool
def create_image_from_prompt(design_input: Union[str, ImageDesignInput]) -> dict:
    ...
```

### Entrada — `Union[str, ImageDesignInput]`

- `str` (retrocompatível): tratado como `ImageDesignInput(prompt=<str>)`.
- `ImageDesignInput` (estruturado): campos abaixo.

| Campo | Tipo | Descrição |
|-------|------|-----------|
| `prompt` | `str` (obrigatório) | Descrição textual da imagem. |
| `art_style` | `str?` | Ex.: "minimalista", "futurista". |
| `color_palette` | `str?` | Ex.: "tons quentes", "monocromático azul". |
| `composition` | `str?` | Ex.: "regra dos terços", "simétrica". |
| `dimensions` | `str?` | Ex.: "1080x1080", "16:9". |
| `negative_prompt` | `str?` | O que evitar. |

> **Nota importante:** hoje a tool envia apenas `prompt` ao Gemini; os demais campos vão só
> para o sidecar de metadados. Para que estilo/paleta/composição afetem a imagem, o
> `image_design_subagent` deve **fundir** esses parâmetros no texto do `prompt` final.

### Retorno — `dict`

```python
{
  "path": "/app/backend/outputs/images/20260705091430.png",  # uso interno; NÃO mostrar
  "url": "/api/images/20260705091430.png",                    # usar no markdown
  "metadata": {"prompt": "...", "art_style": "...", ...},
}
```

Para EXIBIR a imagem ao usuário, use SEMPRE o campo `url`:

```markdown
![descrição](/api/images/20260705091430.png)
```

Um sidecar `..._metadata.json` é salvo junto do PNG em `backend/outputs/images/`.

## Memória de estilos (por thread)

Ferramentas em `backend/src/tools/style_memory_tools.py`, sobre o Store do LangGraph
(namespace `("styles", <thread_id>)`):

- `save_design_style(design_plan, final_prompt)` — salva o plano usado na geração
  bem-sucedida como nova versão (nunca sobrescreve). Chamar após a geração
  bem-sucedida. Nunca salvar planos que falharam.
- `load_design_style(thread_id="")` — recupera o estilo mais recente (thread atual ou, com
  `thread_id`, de outra conversa → transferência de estilo). Use em "na mesma vibe".
- `list_design_styles(thread_id="")` — lista as versões salvas.

## Configuração de ambiente

| Variável | Uso |
|----------|-----|
| `GOOGLE_API_KEY` | Autenticação com a Gemini API (obrigatória para gerar). |
| `POSTGRES_URI` | Checkpointer + Store (memória de estilos e histórico). |

Nenhuma variável nova foi introduzida por este fluxo.

## Referências

- Subagente: `backend/src/agents/subagents/image_design.py`
- Tool: `backend/src/tools/generate_image_tool.py`
- Memória de estilos: `backend/src/tools/style_memory_tools.py`
- Schema: `backend/src/models/image_design.py`
