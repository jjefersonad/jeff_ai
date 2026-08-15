---
name: internet-search
description: "Use this skill whenever the user asks the agent to run a web search via `internet_search` (Tavily). **Antes de chamar a tool, sempre confira a data atual no system prompt (primeira linha) e passe `as_of_date` explícito para eventos após a data de corte do modelo.** Triggers: 'pesquise sobre', 'o que há de novo em', 'notícias de', 'últimas', 'recentes', 'hoje em', 'agora em', 'busque sobre'. NÃO use para: código do repositório (use `grep_project`/`read_project_file`), conceitos já treinados, fatos que não mudam com o tempo (geografia, matemática, história anterior a 2025)."
---

# Internet Search Skill

Pesquisa web no Jeff AI é feita pela tool `internet_search` (Tavily). A change
`current-date-context` adicionou o parâmetro `as_of_date` à tool — a regra
desta skill é: **sempre confira a data antes de pesquisar, e passe
`as_of_date` quando a busca envolver eventos após a data de corte do modelo**.

O motivo é simples: sem a data, o search engine devolve resultados de
qualquer época — incluindo 2024 ou 2025 quando estamos em 2026. O usuário
reportou exatamente esse bug (em 2026-07-13, o agente devolveu resultados
de 2025 para "pesquise sobre IA generativa").

## Antes de buscar

Antes de chamar `internet_search`, **obrigatoriamente**:

1. **Leia a data no topo do system prompt.** É a primeira linha do prompt
   (ex.: `Data atual: 2026-07-14 (UTC)`). Use essa data como base.
2. **Decida se a busca é sobre eventos após a data de corte do modelo.**
   - Se a busca envolve "hoje", "agora", "últimas notícias", "recentes",
     "em 2026", "este mês" → **SIM, é sensível ao tempo.** Passe `as_of_date`
     explícito com a data atual (em ISO `YYYY-MM-DD`).
   - Se a busca envolve "história", "origem de", "conceito de", "documentação
     de" → NÃO. Não passe `as_of_date`.
3. **Se sim, passe `as_of_date`.** A tool aceita string ISO (`YYYY-MM-DD`).
   A data atual pode ser obtida com `datetime.now().date().isoformat()`
   se você precisar de precisão (mas a do prompt basta na maioria dos casos).

## Como usar

```python
# Cenário A — busca sensível ao tempo (recomendado, sempre que envolver "agora"/"hoje")
internet_search(
    query="últimas notícias de IA generativa em 2026",
    as_of_date=datetime.now().date().isoformat()  # → "2026-07-14"
)

# Cenário B — busca atemporal (sem `as_of_date`; a tool sufixa com a data atual automaticamente)
internet_search(query="história do transformer")

# Cenário C — data específica do passado (ex.: notícia de uma data exata)
internet_search(query="GPT-4 anúncio", as_of_date="2023-03-14")
```

A tool **sempre** suffixa a query com `" (as of YYYY-MM-DD)"` antes de
chamar Tavily — se você omitir `as_of_date`, a data atual do sistema é
usada. Se você passar uma data **inválida** (ex.: "ontem"), a tool
retorna erro sem chamar Tavily.

## Parâmetros

| Parâmetro | Tipo | Default | Descrição |
|---|---|---|---|
| `query` | `str` | (obrigatório) | O que pesquisar. |
| `max_results` | `int` | `5` | Número de resultados Tavily. |
| `topic` | `Literal["general", "news", "finance"]` | `"general"` | Categoria da busca. Use `"news"` para buscas sensíveis ao tempo. |
| `include_raw_content` | `bool` | `False` | Inclui o conteúdo bruto das páginas (custo maior de tokens). |
| `as_of_date` | `str` (ISO `YYYY-MM-DD`) ou `None` | `None` (= data atual) | Data de freshness. **Passe explícito quando a busca é sobre eventos após a data de corte do modelo.** |

## Limitações conhecidas

- **PDFs escaneados:** Tavily não lida bem; resultados podem ser vazios.
- **Plano free do Tavily:** não tem `start_date`/`end_date` nativos; a estratégia
  do sufixo é um workaround que funciona em qualquer plano. Se o ranking
  piorar empiricamente (futuro), follow-up pode usar `start_date` nativo.
- **Drift de data:** a data atual é computada no momento da chamada (não no
  import do módulo). Em processos long-running, é a data "real" do turno,
  não a do boot.

## Quando NÃO usar `internet_search`

| Caso | Use em vez de |
|---|---|
| Procurar código no repositório | `grep_project` / `read_project_file` |
| Salvar o resultado de uma URL para RAG | Skill `document-memory` (`ingest_document`) |
| Fato/conceito atemporal | Conhecimento treinável — sem tool |
| Comando de sistema / shell | `run_shell_command` (Tier 4) |

## Histórico

- **2026-07-13:** Bug reportado pelo usuário — o agente devolveu resultados
  de 2025 quando estávamos em 2026-07-13. A cause: o system prompt tinha
  regra passiva ("use `get_date_time_current` quando precisar") e a tool
  `internet_search` não aceitava data.
- **2026-07-14:** Change `current-date-context` fechou o débito — (a) data
  atual virou primeira linha do prompt (sempre visível); (b) tool
  `internet_search` ganhou `as_of_date` (sufixo na query); (c) esta skill
  força o agente a olhar a data antes de buscar.
