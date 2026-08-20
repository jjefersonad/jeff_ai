---
name: image-generation
description: Como planejar e gerar imagens no Jeff AI — perguntas de esclarecimento quando o pedido é vago, catálogo de tipos de asset, checklist anti-"AI slop", template de prompt, o gate de aprovação de create_image_from_prompt (Tier 3) e a memória de estilos por thread.
---

# Image Generation Skill

Geração de imagens é feita **pelo próprio agente**, com as tools no tool set principal.
Não existe subagente dedicado: você lê esta skill, planeja, apresenta o design plan e
chama `create_image_from_prompt` — que **pausa para aprovação humana** antes de gerar.

## Fluxo

```
pedido do usuário
      │
      ├─ vago?  ──► UMA rodada de perguntas objetivas (ver "Esclarecimento")
      │
      ▼
design plan (concept, paleta, estilo, composição, dimensões)
      │
      ▼
create_image_from_prompt(...)      ← Tier 3
      │
      ▼
gate interrupt_on: preview do plano + aprovar / editar / reprovar
      │
 ┌────┴────┐
 ▼         ▼
aprovar   reprovar ──► pergunte qual ajuste o usuário quer ──► novo plano ──► novo gate
 │
 ▼
Gemini → PNG + sidecar JSON ──► save_design_style
```

- **O gate é obrigatório e você não o controla.** `create_image_from_prompt` é Tier 3 no
  `TIER_REGISTRY`: o framework pausa sozinho e mostra o preview do design plan. Você NÃO
  precisa (e não deve) pedir confirmação em texto do tipo "responda ok/sim/prossiga" — a
  aprovação acontece nos botões do gate.
- **Vale por qualquer caminho de chamada.** Se você isolar o planejamento num
  `task(subagent_type="general-purpose")`, o mesmo gate se aplica — o `interrupt_on` é
  herdado. Usar `task` é opcional; útil quando a conversa já está longa e você quer
  contexto limpo para planejar.

## Esclarecimento antes do plano

Se o pedido for **vago**, pergunte pelos essenciais que faltarem ANTES de montar qualquer
design plan. Os essenciais são:

- **Propósito / público-alvo** — para que serve e para quem.
- **Formato de uso** — canal e proporção (post social, hero de site, ícone, impressão…).
- **Restrições de marca** — paleta, tipografia, uso de logo.
- **Texto específico** — a copy exata que deve aparecer, ou "sem texto".

Regras:

- **UMA rodada.** Faça as perguntas objetivas de uma vez só — não um questionário longo,
  não várias idas e voltas. Pergunte só o que falta para produzir um plano de qualidade.
- **Pedido já específico não exige perguntas.** Se o usuário já deu propósito, formato e
  estilo, monte o design plan direto. Perguntar o óbvio é atrito.
- Na dúvida entre perguntar e assumir um default seguro do catálogo de tipos, prefira o
  default e diga qual assumiu — o usuário ainda pode corrigir no gate.

## Regra CRÍTICA — uma imagem por aprovação

NUNCA chame `create_image_from_prompt` mais de UMA vez na mesma resposta. Cada geração tem
sua própria aprovação. Se o usuário pedir várias imagens/variações, gere a PRIMEIRA, aguarde
o resultado, e só então proponha a próxima — uma de cada vez, um gate de cada vez.

## Quando o usuário reprova (reject)

O gate devolve o feedback da rejeição para você. Nesse caso:

1. **Pergunte ao usuário qual ajuste ele quer** (o que não funcionou: conceito? estilo?
   paleta? enquadramento? texto?).
2. Só depois monte um **novo** design plan refletindo o ajuste e apresente de novo.

NUNCA chame `create_image_from_prompt` de novo por conta própria após um reject — cada nova
tentativa exige uma nova decisão humana explícita no gate. Re-tentar sozinho gasta chamadas
do Gemini sem o usuário ter escolhido o novo prompt.

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
> você deve **fundir** esses parâmetros no texto do `prompt` final.

### Retorno — `dict`

```python
{
  "path": "/app/backend/outputs/images/20260705091430.png",  # uso interno; NÃO mostrar
  "url": "http://localhost:8001/api/images/20260705091430.png",  # URL absoluta — usar no markdown
  "metadata": {"prompt": "...", "art_style": "...", ...},
}
```

Para EXIBIR ou COMPARTILHAR a imagem com o usuário, use SEMPRE o campo `url`
(absoluta, montada a partir de `NEXT_PUBLIC_API_URL` / fallbacks). NÃO use `path`.

```markdown
![descrição](http://localhost:8001/api/images/20260705091430.png)
```

Um sidecar `..._metadata.json` é salvo junto do PNG em `backend/outputs/images/`.

## Catálogo de tipos de imagem

Ao planejar uma imagem, identifique se o pedido corresponde a um dos tipos abaixo e aplique
as convenções de dimensão/composição/estilo correspondentes. Essas convenções não são campos
novos — elas se fundem nos campos já existentes de `ImageDesignInput` (ver "Como aplicar o
catálogo" ao final desta seção).

### Banner / post social
- **Dimensões:** 1200x628 ou proporção 16:9 / 1.91:1.
- **Composição:** ponto focal único; evite colagens.
- **Estilo:** texto curto, legível em tamanho de feed; uma mensagem central por imagem.

### Ícone / logo
- **Dimensões:** quadradas — 512x512 ou 1024x1024.
- **Composição:** centralizada, simétrica.
- **Estilo:** `art_style` simples/flat.
- **Evitar:** use `negative_prompt` para afastar texto denso ou detalhe excessivo.

### Hero image
- **Dimensões:** largas — 1920x1080 ou 21:9.
- **Composição:** espaço negativo reservado para overlay de título/CTA.
- **Estilo:** `art_style`/paleta consistentes com a marca, nunca decoração genérica.

### Thumbnail
- **Dimensões:** otimizadas para miniatura — ex. 1280x720.
- **Composição:** alto contraste, ponto focal único legível mesmo em tamanho reduzido.
- **Estilo:** texto grande (se houver) em vez de copy densa.

### Foto de produto
- **Dimensões:** conforme o canal — ex. 1080x1080 ou 16:9.
- **Composição:** mostrar uma interface/fluxo plausível, nunca fragmentos decorativos de UI.
- **Estilo:** `art_style` realista/estúdio.

### Avatar
- **Dimensões:** quadradas — 512x512.
- **Composição:** centralizada, close-up (rosto/personagem/mascote); fundo simples, sem
  competir com o sujeito.
- **Evitar:** use `negative_prompt` para afastar elementos cortados nas bordas.

### Ilustração
- **Dimensões:** conforme o canal de destino — sem convenção fixa própria do tipo.
- **Composição:** priorizar um conceito visual coerente com a mensagem, em vez de repetir o
  título literalmente.
- **Estilo:** liberdade maior de `art_style` — este é o tipo menos restritivo em composição.

Esses 7 tipos (banner/post social, ícone/logo, hero image, thumbnail, foto de produto, avatar,
ilustração) são exaustivos para efeitos de cobertura de cenário — não é uma lista "pelo menos
estes".

### Como aplicar o catálogo

Funda as convenções do tipo identificado exclusivamente nos campos
JÁ EXISTENTES de `ImageDesignInput` — `prompt`, `art_style`, `composition` e `dimensions` (e,
quando fizer sentido, `negative_prompt`). NUNCA introduza, referencie ou exija um campo novo
(`type`, `asset_type` ou equivalente) — nem no schema de `ImageDesignInput`, nem na chamada a
`create_image_from_prompt`. A tradução segue a regra já documentada de "fundir no prompt final"
sempre que o tipo afeta estilo, paleta ou composição.

Se o pedido do usuário não corresponder a nenhum tipo do catálogo (ex.: "um wallpaper para meu
desktop"), siga o processo de planejamento genérico já existente — pergunte pelos essenciais
que faltarem ou use julgamento próprio de estilo/composição/dimensões — sem bloquear a geração
por falta de correspondência com um tipo catalogado.

## Checklist "AI Slop" (evitar por padrão)

Estes são os tiques do design gerado por máquina. Eles se agrupam porque são exatamente o que
um modelo de imagem/layout busca por padrão — e é exatamente por isso que soam genéricos. O
objetivo não é decorar uma lista negra; é reconhecer a família para evitar a próxima variante
também. O princípio de fundo: todo elemento deve justificar sua presença carregando significado
ou hierarquia. Se está ali só para parecer "desenhado", corte.

Evite os itens abaixo a menos que o usuário peça explicitamente por um deles:

- **Eyebrow pill acima do título.** O badge arredondado com texto ("✨ INTRODUCING", "NEW",
  "v2.0") flutuando acima do H1. Quase nunca acrescenta informação que o título já não carrega,
  e é o tique de layout de IA mais comum. Comece pelo próprio título.
- **Botões com gradiente ou brilho.** Preenchimentos multicoloridos, glow neon, ou brilho
  animado em CTAs. Use uma cor de destaque sólida, com sombra plana ou bem sutil. Um botão deve
  parecer clicável, não radioativo.
- **O gradiente padrão roxo→rosa/violeta de "tech".** Fundos índigo-para-magenta (o "lavado de
  startup de IA" genérico) sinalizam template, não marca. Ancore a cor na paleta real do
  produto. Um gradiente é aceitável quando é contido e alinhado à marca — o problema é recorrer
  a *esse* gradiente por padrão.
- **Ornamentos de emoji e brilho (✨/🚀/⚡).** Emoji decorativo usado como elemento de design em
  vez de conteúdo. Empobrecem a composição e datam a peça instantaneamente.
- **Glassmorphism em todo lugar.** Cartões translúcidos com blur empilhados em profundidade sem
  motivo funcional. Um único cartão em primeiro plano com blur pode funcionar; uma cena inteira
  deles é slop.
- **Imagética genérica de startup.** Dashboards flutuantes sem contexto, fotos de aperto de mão,
  metáforas de foguete/lâmpada, abstrações 3D vagas — blobs, esferas glossy, isométricos
  aleatórios, orbes de gradiente que não representam nada.
- **Decoração no lugar de hierarquia.** Sombras pesadas em todo elemento, border-radius
  exagerado em tudo, texto com glow neon, e tudo centralizado sem contraste de tamanho/peso.
  Polish vem de hierarquia clara e espaçamento, não de efeitos.
- **Copy densa.** Parágrafos, subtítulos com múltiplas frases, ou listas de features empilhadas
  dentro de uma imagem. Se não dá para ler em tamanho de thumbnail, não pertence à imagem — mova
  para o texto ao redor.
- **Credibilidade falsa.** Fileiras de logos "Trusted by" inventadas, avaliações com estrelas
  placeholder, ou trios de estatísticas com números inventados. Use ativos reais ou omita.

Se o usuário *quiser* um desses (ex.: "quero aquele visual glassy com gradiente"), execute bem —
esta lista trata de padrões default, não de proibição absoluta.

## Template de prompt

Use esta estrutura ao montar o `prompt` final para `create_image_from_prompt` (funda os campos
estruturados de `ImageDesignInput` no texto conforme a "Nota importante" acima):

```text
Create a [tipo de asset] for [produto/empresa/campanha].

Goal: [objetivo de conversão ou mensagem]
Audience: [público específico]
Format: [dimensões/proporção/canal]
Composition: [sujeito principal, layout, ponto focal, profundidade, enquadramento]
Style: [estilo visual, medium, sensação de marca]
Color and lighting: [paleta, contraste, mood]
Text: [texto exato, ou "no text"]
Brand constraints: [uso de logo, direção tipográfica, do/don't]
Avoid: [clichês visuais específicos, poluição visual, objetos errados, alegações inseguras]
```

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
| `NEXT_PUBLIC_API_URL` | Origem pública do API para a `url` absoluta no retorno da tool (fallback: `BASE_URL` → `FRONTEND_ORIGIN` → `http://localhost:3000`). |

## Referências

- Tool: `backend/src/tools/generate_image_tool.py`
- Gate (Tier 3 + preview do plano): `backend/src/agents/unified/tier_config.py`
  (`TIER_3_TOOLS`, `_preview_for_create_image_from_prompt`)
- Memória de estilos: `backend/src/tools/style_memory_tools.py`
- Schema: `backend/src/models/image_design.py`
