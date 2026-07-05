---
name: image-generation
description: Documenta o fluxo de geração de imagens do Jeff AI — o image_design_subagent (planejamento + aprovação obrigatória via interrupt_on), a tool create_image_from_prompt (Union[str, ImageDesignInput] -> dict) e a memória de estilos por thread.
---

# Image Generation Skill

Geração de imagens no Jeff AI é feita por um **subagente de design** (`image_design_subagent`)
que planeja a imagem e **exige aprovação explícita do usuário** antes de gerar (evitando gasto
de tokens com imagens inadequadas). A geração em si é feita pela tool `create_image_from_prompt`
(Google Gemini), sob um gate de aprovação (`interrupt_on`).

## Arquitetura do fluxo

```
usuário → orquestrador (agent) ─┐
         assistant ─────────────┴─► task(name="image_design_subagent")
                                        │  1. analisa contexto
                                        │  2. monta design plan (concept, paleta, estilo…)
                                        │  3. apresenta o plano
                                        │  4. decide chamar create_image_from_prompt
                                        ▼
                                 interrupt_on PAUSA o grafo  ← aprovação humana
                                        │  Command(resume=…): approve | edit | reject
                                        ▼
                                 create_image_from_prompt → Gemini → PNG + sidecar JSON
```

- **Quem delega:** o orquestrador (`requirements_specialist`) e o `assistant` registram o
  `image_design_subagent` como subagente direto e delegam via `task(...)`. Um SubAgent NÃO
  chama `task()` nem alcança subagentes irmãos, então o `fullstack_subagent` apenas **defere**
  tarefas de imagem (não gera).
- **Aprovação obrigatória:** garantida pelo framework via `interrupt_on`; o subagente NUNCA
  gera sem que o resume de aprovação seja recebido.

## Regra CRÍTICA de aprovação

NUNCA gere imagem sem aprovação explícita. O `image_design_subagent` apresenta o design plan
e o `interrupt_on={"create_image_from_prompt": ...}` pausa o grafo antes de executar a tool.
Decisões válidas (`allowed_decisions`): **`approve`**, **`edit`**, **`reject`**.

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

- `save_design_style(design_plan, final_prompt)` — salva o plano APROVADO como nova versão
  (nunca sobrescreve). Chamar só após aprovação + geração. Nunca salvar planos rejeitados.
- `load_design_style(thread_id="")` — recupera o estilo mais recente (thread atual ou, com
  `thread_id`, de outra conversa → transferência de estilo). Use em "na mesma vibe".
- `list_design_styles(thread_id="")` — lista as versões salvas.

## Configuração de ambiente

| Variável | Uso |
|----------|-----|
| `GOOGLE_API_KEY` | Autenticação com a Gemini API (obrigatória para gerar). |
| `POSTGRES_URI` | Checkpointer + Store (aprovação/interrupt e memória de estilos). |

Nenhuma variável nova foi introduzida por este fluxo.

## Referências

- Subagente: `backend/src/agents/subagents/image_design.py`
- Tool: `backend/src/tools/generate_image_tool.py`
- Memória de estilos: `backend/src/tools/style_memory_tools.py`
- Schema: `backend/src/models/image_design.py`
- Docs deepagents (human-in-the-loop / subagents): ver `docs/links_uteis.md`
