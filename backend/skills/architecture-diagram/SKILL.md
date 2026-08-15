---
name: architecture-diagram
description: Gere um diagrama de **arquitetura** visual profissional (HTML autocontido com SVG inline) a partir de uma descrição em texto plano do sistema. Use APENAS para diagramas de arquitetura (componentes + conexões, estilo "boxes-and-arrows"). Para fluxos, sequências, ER, classes ou state machines, use `diagram-creator` (Mermaid).
---

# Architecture Diagram Generator

Skill baseado em [Cocoon-AI/architecture-diagram-generator](https://github.com/Cocoon-AI/architecture-diagram-generator) (MIT) — gera um ficheiro HTML autocontido com SVG inline, tema dark, **paleta semântica do Jeff AI design system** (alinhada com `chart-1..5` do frontend) por tipo de componente, e botões de export (Copy / PNG / PDF) embutidos.

## Quando usar

Considere esta skill quando a descrição é naturalmente um grafo de **componentes e conexões** (boxes-and-arrows):

- **Arquitetura de sistema** — frontend, API, DB, cache, filas, cloud services.
- **Topologia de deployment** — regiões, VPCs, subnets, balanceadores.
- **Pipeline de dados** — fontes → transformações → sinks.
- **Bounded contexts / microserviços** — serviços e como se chamam.

**NÃO use para:**
- Sequence diagrams (chamadas ordenadas entre atores) → `diagram-creator` (`sequenceDiagram`).
- ER diagrams (modelo de dados) → `diagram-creator` (`erDiagram`).
- Class diagrams (hierarquia de classes) → `diagram-creator` (`classDiagram`).
- State machines → `diagram-creator` (`stateDiagram-v2`).
- Fluxogramas simples → `diagram-creator` (`flowchart`) — mais rápido, sem file write.

## Input esperado

Uma descrição do sistema, em qualquer formato razoável. Aceita:

- **Lista plana** de componentes e conexões:
  ```
  - React frontend
  - Node.js API
  - PostgreSQL
  - Redis cache
  - Hosted on AWS CloudFront
  ```
- **Parágrafo livre** descrevendo a arquitetura.
- **Markdown** com headers, listas, ênfase.
- **Texto colado** de análise de código (Cursor/Claude Code/etc.).

Se o user pedir "diagrama de arquitetura" sem mais detalhe, **faça 2-3 perguntas curtas** para clarificar:
1. Quais são os componentes principais? (frontend/backend/DB/etc.)
2. Há serviços cloud específicos? (AWS/GCP/Azure/on-prem)
3. Há agrupamentos/boundaries? (VPCs, security groups, regiões)

## Output

Um **único ficheiro `.html`** em `backend/outputs/documents/html/<timestamp>-<slug>.html` contendo:

- SVG inline com todos os componentes e setas (não há SVG externo).
- CSS dark theme (Slate-950, JetBrains Mono fallback para `monospace` se sem internet).
- 3 cards de sumário com detalhes chave.
- Toolbar com botões **Copy / PNG / PDF** (via `html2canvas` + `jsPDF` por CDN — degrada gracefully se offline).

O ficheiro é servido por `/api/files/html/<file>` (route já configurada em `documents_router.py` com kind `html`, `text/html` mime, `X-Content-Type-Options: nosniff`). O browser renderiza **inline** (sem `Content-Disposition: attachment`) para que o diagrama abra diretamente.

## Workflow

### 1. Ler o template

Antes de escrever o HTML, leia o template:

```
backend/skills/architecture-diagram/resources/template.html
```

Use a tool `read_file` (Tier 1, sem gate). O template é autocontido e mostra exemplos de cada padrão visual.

### 2. Substituir o conteúdo

Edite **in-place** o template, mantendo a estrutura HTML intacta. Substituir:

| Placeholder | Substituir por |
|---|---|
| `[PROJECT NAME]` no `<title>` | Nome curto do sistema |
| `<h1>[PROJECT NAME] Architecture</h1>` | Nome curto + "Architecture" |
| `<p class="subtitle">[Subtitle description]</p>` | Frase de uma linha descrevendo o sistema |
| O `<svg>` inteiro entre `<!-- Main Diagram -->` e `</div>` | Diagrama novo (ver secção "Componentes") |
| Os 3 `<div class="card">` | Sumários com highlights (ver secção "Cards") |
| `<p class="footer">[Project Name] • [Additional metadata]</p>` | Nome + data ou metadata breve |

**Não inventar:** Se o user não disse algo (ex: protocolo HTTPS vs HTTP), escreva o mais comum e seguro (HTTPS).

### 3. Componentes — paleta semântica (Jeff AI Design System)

**Cores alinhadas com o tema dark do frontend** — derivadas dos tokens `chart-1..5` do Tailwind config (`globals.css:183-187`). Mantêm WCAG AA no background `#020617` e casam visualmente com os componentes do app (lucide icons, charts, badges).

| Role | Stroke (HSL) | Fill (alpha 0.18) | Tipo | Use para |
|---|---|---|---|---|
| **Frontend** | `hsl(220 70% 50%)` | `hsl(220 70% 50% / 0.18)` | UI, cliente | React, browser, mobile app, edge device |
| **Backend** | `hsl(160 60% 45%)` | `hsl(160 60% 45% / 0.18)` | API, server | FastAPI, Node, microservice |
| **Data** | `hsl(280 65% 60%)` | `hsl(280 65% 60% / 0.18)` | DB, cache, queue | Postgres, Redis, Kafka, S3 |
| **Cloud** | `hsl(30 80% 55%)` | `hsl(30 80% 55% / 0.18)` | Cloud, infra | AWS, GCP, K8s, CDN, LB |
| **Security** | `hsl(340 75% 55%)` | `hsl(340 75% 55% / 0.18)` | Auth, secrets | OAuth, JWT, Vault, security group |
| **External** | `hsl(0 0% 65%)` | `hsl(0 0% 65% / 0.12)` | Genérico | Sistema externo, third-party |

**Tipografia no SVG** (consistente em todos os componentes):
- **Label principal** (título do componente): `fill="hsl(220 13% 95%)"` — branco off, `font-weight="600"`, `font-size="11"`
- **Subtítulo** (linha de baixo, ex: tecnologia/porta): `fill="hsl(220 9% 65%)"` — cinza claro, `font-weight="400"`, `font-size="9"`
- **Caption** (footer/aviso): `fill="hsl(220 9% 46%)"` — cinza médio, `font-size="8"`
- **Accent** (highlight): `fill="hsl(38 92% 50%)"` — amarelo (warnings, status)

**Shapes** (todos os componentes):
- Border radius padrão: `rx="6"` para boxes simples, `rx="8"` para containers
- Stroke width: `1.5` para componentes, `1` para boundaries/security groups
- Boundary/cloud regions: `stroke-dasharray="8,4"`
- Security group: `stroke-dasharray="4,4"` com `fill="transparent"`
- Auth flow: `stroke-dasharray="5,5"`

### 4. Padrões de componente

**Componente simples** (rectângulo com 1 linha de label) — exemplo Backend:
```svg
<rect x="200" y="280" width="110" height="50" rx="6"
      fill="hsl(160 60% 45% / 0.18)" stroke="hsl(160 60% 45%)" stroke-width="1.5"/>
<text x="255" y="300" fill="hsl(220 13% 95%)" font-size="11" font-weight="600" text-anchor="middle">API Server</text>
<text x="255" y="316" fill="hsl(220 9% 65%)" font-size="9" text-anchor="middle">FastAPI :8000</text>
```

**Componente multi-linha** (lista de items) — exemplo Cloud:
```svg
<rect x="200" y="380" width="110" height="100" rx="6"
      fill="hsl(30 80% 55% / 0.18)" stroke="hsl(30 80% 55%)" stroke-width="1.5"/>
<text x="255" y="400" fill="hsl(220 13% 95%)" font-size="11" font-weight="600" text-anchor="middle">S3 Buckets</text>
<text x="255" y="420" fill="hsl(220 9% 65%)" font-size="8" text-anchor="middle">• bucket-one</text>
<text x="255" y="434" fill="hsl(220 9% 65%)" font-size="8" text-anchor="middle">• bucket-two</text>
```

**Boundary / region** (rectângulo tracejado grande a envolver componentes) — exemplo Cloud/AWS:
```svg
<rect x="160" y="40" width="820" height="620" rx="12"
      fill="hsl(30 80% 55% / 0.05)" stroke="hsl(30 80% 55%)"
      stroke-width="1" stroke-dasharray="8,4"/>
<text x="172" y="58" fill="hsl(30 80% 55%)" font-size="10" font-weight="600">AWS Region: us-west-2</text>
```

**Security group** (rectângulo tracejado pequeno + label) — exemplo Security:
```svg
<rect x="350" y="265" width="120" height="80" rx="8"
      fill="transparent" stroke="hsl(340 75% 55%)" stroke-width="1"
      stroke-dasharray="4,4"/>
<text x="358" y="279" fill="hsl(340 75% 55%)" font-size="8">sg-name :port</text>
```

### 5. Setas e conexões

**Seta simples** (sempre com `marker-end="url(#arrowhead)"`):
```svg
<line x1="310" y1="305" x2="358" y2="305"
      stroke="hsl(220 13% 65%)" stroke-width="1.5"
      marker-end="url(#arrowhead)"/>
```

**Seta colorida** (frontend → backend): use a cor da role de origem:
```svg
<line x1="130" y1="305" x2="198" y2="305"
      stroke="hsl(220 70% 50%)" stroke-width="1.5"
      marker-end="url(#arrowhead)"/>
<text x="164" y="299" fill="hsl(220 9% 65%)" font-size="9" text-anchor="middle">HTTPS</text>
```

**Seta tracejada** (auth / async / dados) — sempre Security color:
```svg
<path d="M 80 140 L 80 200 Q 80 220 100 220 L 200 220 Q 220 220 220 240 L 220 278"
      fill="none" stroke="hsl(340 75% 55%)" stroke-width="1.5"
      stroke-dasharray="5,5"/>
<text x="150" y="210" fill="hsl(340 75% 55%)" font-size="8">JWT + PKCE</text>
```

### 6. Layout — viewBox 1000x680

Posicione componentes com **fluxo visual lógico**:
- **Externos** à esquerda (Users, Browser)
- **Camadas** da esquerda para a direita: Users → Auth → Frontend → API → DB
- **Cloud boundaries** como retângulos grandes a envolver cloud services
- **Security groups** como retângulos pequenos a envolver recursos protegidos

Mantenha **margens de ~30px** entre componentes. Não sobreponha setas com texto.

### 7. Cards de sumário

Os 3 `<div class="card">` abaixo do SVG resumem o sistema. Use a paleta para indicar a categoria de cada card:

```svg
<div class="card">
  <div class="card-header">
    <div class="card-dot" style="background: hsl(280 65% 60%)"></div>
    <h3>Stack & Frameworks</h3>
  </div>
  <ul>
    <li>• React 18 + TypeScript</li>
    <li>• FastAPI (Python 3.12)</li>
    <li>• PostgreSQL 16 + pgvector</li>
  </ul>
</div>
```

Boas categorias para os 3 cards:
- **Stack & Frameworks** (linguagens, runtimes, frameworks chave)
- **Infrastructure** (cloud, regiões, CDN, IaC)
- **Security & Compliance** (auth, encryption, observability)

### 8. Escrever o ficheiro

Depois de o HTML estar completo, escreva em `backend/outputs/documents/html/<timestamp>-<slug>.html` usando `write_file` (Tier 2 — auto-roda, frontend notifica):

```
backend/outputs/documents/html/20260801120000-jeff-ai-architecture.html
```

O `documents_router.py` resolve `kind=html` para `DOCUMENTS_DIR/html` (mesmo diretório-base que `docx|xlsx|pptx`). Mantém um único ponto de montagem `/api/files/<kind>/<file>` para todos os ficheiros gerados.

**Slug:** lowercase, hyphen-separated, derivado do nome do projeto (ex: "Jeff AI Platform" → `jeff-ai-platform`).

Após `write_file` retornar sucesso, **emita a URL no markdown** para o user poder abrir:

```markdown
📐 Diagrama de arquitetura: [Jeff AI Platform](/api/files/html/20260801120000-jeff-ai-architecture.html)

**Componentes principais:** Frontend (azul), API (teal), Database (violeta), Cloud (laranja), Security (rosa).
**Conexões:** N utilizadores, 1 API, 2 DBs, 1 cache.
```

**Sempre use `url` no markdown, nunca `path`.** (Igual à regra de imagens e Office docs.)

## Convenções

- **NÃO perguntar permissão** para gerar o diagrama — esta skill é Tier 2 (auto-roda).
- **NÃO pedir clarificações excessivas** — se a descrição for vaga, escolhe as opções mais prováveis e gera. O user pode iterar.
- **Iterar** — se o user pedir "adiciona Kafka" ou "move a DB para o meio", re-lê o ficheiro atual, edita in-place, escreve de volta.
- **Não inventar ferramentas** — se a descrição diz "Postgres" sem versão, escreve "PostgreSQL". Não inventar "Redis Sentinel" se o user só disse "Redis".
- **Conservador com cloud** — se não mencionar cloud, use slate (External). Se mencionar AWS, use amber.

## Pré-requisitos / Limitações

- **Dependências CDN** (degrada gracefully se offline): Google Fonts (JetBrains Mono), html2canvas, jsPDF. Se o user estiver offline, o diagrama renderiza em monospace padrão e os botões Copy/PNG/PDF falham silenciosamente.
- **Não substitui `diagram-creator`** — para sequence/ER/class/state, continue a usar Mermaid.
- **Sem iteração visual** — esta skill não tem preview iterativo. O user precisa de abrir o ficheiro no browser para ver. Para iteração rápida, prefira Mermaid.
- **Tier 2 (file write)** — cada geração escreve um ficheiro novo. Em produção o user recebe notificação no front (igual a Office docs).

## Referências

- Origem: [Cocoon-AI/architecture-diagram-generator](https://github.com/Cocoon-AI/architecture-diagram-generator) (MIT)
- Template: `backend/skills/architecture-diagram/resources/template.html`
- Rota de serving: `backend/src/infrastructure/web/documents_router.py` (kind `html`)
- Skill irmã: `diagram-creator` (Mermaid, Tier 1, client-side)
