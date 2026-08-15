---
name: sdd
description: "Use this skill whenever the user wants to run Spec-Driven Development (SDD) for a feature of the Jeff AI product itself — spec-kit style artifacts (constitution, spec, plan, tasks) written to backend/outputs/.specify/. Triggers include: 'crie a spec desta feature', 'rode o pipeline SDD', 'escreva o plano técnico', 'gere as tasks', 'valide os artefatos SDD', or any request to produce/update a constitution.md, spec.md, plan.md, tasks.md, data-model.md under .specify/specs/. This is the INTERNAL SDD feature of the Jeff AI product (for its users) — it is NOT the OpenSddRag MCP server used to develop Jeff AI itself. Do not confuse the two, and never invoke a subagent for this — the SDD pipeline runs entirely on the tools in src/tools/sdd_tools.py."
---

# SDD — Spec-Driven Development como skill

## Visão geral

O pipeline SDD (spec-kit) roda inteiramente **sobre as tools que já existem** em
`src/tools/sdd_tools.py`: `get_next_feature_number`, `create_feature_directory`,
`load_template`, `validate_artifact`, `get_sdd_state` — mais `read_file`/`write_file`/
`edit_file` (já disponíveis no agente) para ler e escrever o conteúdo de cada
artefato. **Nenhum subagente é invocado.** As instruções abaixo substituem os 7
subagentes de `src/agents/sdd/subagents/` — o conteúdo técnico de cada fase vem
deles (são um guia bom); o que muda é a embalagem: um `SKILL.md`, não um
`SubAgent` com contexto isolado.

> **Fronteira:** este é o SDD **interno** do Jeff AI — uma feature do produto,
> para os usuários dele, que escreve em `backend/outputs/.specify/`. **Não** é o
> OpenSddRag (servidor MCP usado para desenvolver o próprio Jeff AI, acessível
> via `/opsr:*`). Não confunda os dois nem chame o OpenSddRag a partir desta skill.

> **Envelope de permissões:** esta skill é conselho ao modelo, nunca concessão de
> acesso. Se `write_file`/`edit_file` não estiverem no envelope concedido para a
> tarefa, os passos que escrevem artefato ficam bloqueados normalmente — a skill
> não amplia o que o agente pode fazer.

## As 7 fases

```
constitution → specify → clarify → plan → analyze → tasks → implement
```

Cada fase é independente: o usuário pode pedir **só uma** ("escreva a spec desta
feature") e você executa **apenas aquela fase** — não force o pipeline inteiro.
Use `get_sdd_state(feature_dir)` quando precisar saber que fases já existem e
qual é a próxima pendente (campo `next_phase` da resposta).

### Fase 0 — descobrir/criar o diretório da feature

Antes de qualquer fase, se a feature ainda não tem diretório:
1. `get_next_feature_number()` → número de 3 dígitos (ex.: `"004"`).
2. `create_feature_directory(feature_name="<kebab-case>", feature_number="<NNN>")`
   → cria `backend/outputs/.specify/specs/{NNN}-{feature}/` com placeholders para
   `spec.md`, `plan.md`, `tasks.md`, `data-model.md`, `research.md`,
   `quickstart.md`, `contracts/api-spec.json`, e garante `memory/constitution.md`.

Se a feature já existe, use `get_sdd_state("backend/outputs/.specify/specs/{NNN}-{feature}")`
para retomar do ponto certo em vez de recriar.

### Fase 1 — constitution

Documento fundacional em `backend/outputs/.specify/memory/constitution.md`,
**compartilhado entre todas as features** (não vive no diretório da feature).
Só atualize quando os fundamentos do projeto mudarem — é um documento vivo,
conservador.

1. `load_template("constitution")`.
2. Leia o arquivo existente (`read_file`) para não sobrescrever sem necessidade.
3. Escreva/atualize com estas seções (os títulos abaixo são **obrigatórios
   literalmente** — `validate_artifact` os procura por substring, case-insensitive):
   - `## Core Principles` — 3–5 princípios imutáveis, tecnologia-agnósticos, com sub-regras.
   - `## Technology Constraints` — tecnologias permitidas/proibidas, cada uma com justificativa.
   - `## Development Workflow` — branch strategy, code review, testes, CI/CD.
   - `## Quality Gates` — checklist concreto que precisa passar antes do merge.
   - `## Governance` — processo de emenda e cadência de revisão.

### Fase 2 — specify

`spec.md` no diretório da feature. Foco exclusivo em **O QUÊ e POR QUÊ** — nunca
tecnologia, framework, banco de dados ou detalhe de implementação.

1. `load_template("spec")`.
2. Leia `memory/constitution.md` para contexto.
3. Escreva `spec.md` com estas seções (títulos obrigatórios para `validate_artifact`):
   - `## Overview` — problema que está sendo resolvido, por que importa, e a
     solução proposta em alto nível (o que será construído).
   - `## User Scenarios` — pelo menos 3 histórias, formato
     "Como [papel], eu quero [ação], para que [benefício]", cada uma com
     critérios de aceite testáveis e independentes; inclua uma subseção de
     **Edge Cases** (tabela: cenário → comportamento esperado — entrada
     inválida, não encontrado, concorrência).
   - `## Functional Requirements` — FR-001, FR-002, ... numerados, com
     prioridade, história relacionada e critério de aceite.
   - `## Non-Functional Requirements` — performance, segurança, confiabilidade,
     com metas mensuráveis.
   - `## Key Entities` — entidades de domínio com descrição.
4. Checklist antes de escrever: toda US tem critério de aceite independente;
   todo FR é numerado e rastreável a uma US; nenhuma menção a tecnologia ou
   implementação; edge cases cobrem entrada inválida, não encontrado e
   concorrência; critérios de sucesso são mensuráveis, não subjetivos.

### Fase 3 — clarify

Analisa `spec.md` em busca de áreas subespecificadas e anexa uma seção de
clarificações — não gera um artefato novo.

1. Leia `spec.md`.
2. Para cada lacuna (error handling, edge cases, validação de dados, segurança,
   performance, integração, fluxos de UX), produza uma entrada:
   ```
   ### Q{N}: {Título da pergunta}
   **Question:** {a ambiguidade}
   **Context:** {seção ou história onde aparece a lacuna}
   **Impact:** {história/requisito afetado se ficar sem resposta}
   **Recommendation:** {resposta proposta com justificativa}
   ```
3. Anexe (`edit_file`) uma seção `## Clarifications` ao `spec.md` com todas as
   entradas, e um `## Clarification Summary` com totais (crítico/bloqueante,
   importante, nice-to-have).
4. Seja cirúrgico: não reformule perguntas já respondidas claramente no spec;
   foque no que de fato bloqueia a implementação.

### Fase 4 — plan

Quatro a cinco artefatos técnicos no diretório da feature, todos rastreáveis a
um requisito do spec ou princípio da constituição.

1. Leia `spec.md` e `memory/constitution.md`.
2. `load_template("plan")`, `load_template("data-model")`, `load_template("api-spec")`.
3. Escreva:
   - **`plan.md`** com estas seções (obrigatórias para `validate_artifact`):
     `## Architecture Overview`, `## Technology Stack` (com versões e
     justificativa ligada às restrições da constituição), `## Component Design`
     (responsabilidade, dependências, interfaces por componente), `## Data Flow`,
     `## API Design` (tabela de endpoints: método, path, request/response),
     `## Implementation Phases` (mapeadas às prioridades das user stories),
     `## Risk Assessment`, `## Constitution Compliance`.
   - **`data-model.md`** com: `## Entity Relationship Overview` (diagrama em
     texto), `## Entities` (campos, tipos, constraints, índices, relações,
     regras de validação de cada entidade), enumerações se houver, notas de
     migração. Inclua também uma seção `## Validation Rules` — as três são
     obrigatórias para `validate_artifact`.
   - **`contracts/api-spec.json`** — OpenAPI 3.0 com todos os endpoints do
     `plan.md`, schemas batendo com o data model, respostas de erro padrão
     (400, 401, 404, 409, 500).
   - **`research.md`** — decisões de tecnologia, alternativas consideradas,
     por que cada escolha foi feita, trade-offs.
   - **`quickstart.md`** — pré-requisitos, setup, como rodar local, como rodar testes.

### Fase 5 — analyze

Validação cruzada de consistência e cobertura entre todos os artefatos —
não é uma fase de geração.

1. Leia `spec.md`, `plan.md`, `tasks.md` (se existir), `data-model.md` e
   `memory/constitution.md`.
2. Rode `validate_artifact` em cada um (tipos válidos: `constitution`, `spec`,
   `plan`, `tasks`, `data-model`).
3. Verifique cruzado:
   - **Cobertura:** todo FR do spec tem task correspondente (se `tasks.md`
     existir); toda user story é coberta por uma fase do plan; toda entidade do
     data model aparece em Key Entities do spec.
   - **Consistência:** escolhas de tecnologia do plan não violam Technology
     Constraints da constituição; entidades do data model batem com os
     endpoints do plan; endpoints cobrem as interações das user stories;
     dependências do tasks.md seguem a ordem das Implementation Phases do plan.
   - **Completude:** todas as seções exigidas por template presentes; sem
     placeholder/TODO restante; sem referência não definida entre artefatos.
4. Escreva `validation-report.md` no diretório da feature com: status geral
   (PASS/WARN/FAIL), resultado por artefato (via `validate_artifact`), achados
   de consistência cruzada com referência de arquivo (ex.: "spec.md:FR-003 sem
   task correspondente"), recomendações acionáveis. Se houver FAIL, declare
   explicitamente quais fases precisam ser refeitas.

### Fase 6 — tasks

`tasks.md` — quebra o plano em tasks executáveis e ordenadas.

1. Leia `spec.md` e `plan.md`.
2. `load_template("tasks")`.
3. Escreva `tasks.md`. Seções obrigatórias para `validate_artifact`:
   `## Dependency Graph` (diagrama em texto das dependências entre fases),
   uma fase literalmente rotulada `**Phase 1:** Setup` (o texto `Phase 1:` é
   checado por substring), e ao menos um marcador `## Checkpoint`.
   - Formato de task: `- [ ] T{NNN} [P] [US{N}] {Descrição} em {file_path} (Deps: T{NNN}, ...)`.
   - `[P]` = paralelizável (sem dependência de outra task na mesma fase).
   - Fases em ordem: 1. Setup (geralmente tudo `[P]`) → 2. Foundational → 
     3..N. uma fase por user story, prioridade P1 primeiro (dentro de cada:
     Models `[P]`, Repository `[P]`, Service, Endpoint, Tests `[P]`) →
     N+1. Integration → N+2. Polish.
   - Após cada fase de user story, inclua um `Checkpoint` com o que verificar
     (critério de aceite do spec) e o resultado de teste esperado.
   - Regras: nunca referenciar uma task antes dela ser definida; models antes
     de services, services antes de endpoints; todo file path concreto; toda
     user story tem ao menos Model, Service, Endpoint e Test.

### Fase 7 — implement

Executa as tasks de `tasks.md`, em ordem de dependência estrita.

1. Leia `tasks.md`, `plan.md`, `data-model.md`, `spec.md`.
2. Execute: Fase 1 (Setup) → Fase 2 (Foundational) → fases de user story em
   ordem de prioridade → dentro de cada fase, respeite as dependências
   (`[P]` pode ser em qualquer ordem).
3. Para cada task: leia o arquivo existente antes de modificar; crie/edite
   seguindo os padrões do `plan.md` e o schema exato do `data-model.md`; siga
   os contratos de `contracts/api-spec.json`; marque `[x]` em `tasks.md` ao
   concluir.
4. Ao final: confirme que todos os arquivos criados/modificados existem;
   confira consistência com `plan.md`; atualize `quickstart.md` se algum passo
   de setup mudou.

Esta fase escreve/edita arquivos de código do repositório real — está sujeita
ao envelope da tarefa e aos tiers normais (`edit_file`/escrita de arquivo novo
passam pelos gates de sempre; nada aqui os contorna).

## Loop de validação (retry)

Depois de escrever qualquer artefato dos tipos conhecidos por `validate_artifact`
(`constitution`, `spec`, `plan`, `tasks`, `data-model`):

1. Rode `validate_artifact(file_path=..., artifact_type=...)`.
2. Se `status` for `FAIL` ou `WARN`: releia as seções ausentes (campo `checks`,
   entradas com `"status": "FAIL"`), reescreva a fase preenchendo exatamente
   essas seções, e valide de novo.
3. Só considere a fase concluída quando `status == "PASS"` — ou, para `WARN`,
   quando o usuário aceitar explicitamente publicar com lacunas.

## Estado da feature

`get_sdd_state(feature_dir)` devolve, por fase, `complete` / `placeholder` /
`missing`, mais `next_phase` (próxima fase rastreada incompleta) e
`pipeline_complete` (bool). Use antes de decidir se uma fase pedida precisa de
uma fase anterior primeiro — mas nunca force fases não pedidas pelo usuário.

## O que esta skill NÃO faz

- Não invoca `task()` nem nenhum subagente — todo o trabalho é leitura/escrita
  de arquivo mais as 5 tools de `sdd_tools.py`.
- Não decide sozinha ampliar o que pode escrever: se o envelope da tarefa não
  concede `write_new`/`write_existing`, a escrita do artefato é bloqueada como
  qualquer outra tool fora do envelope.
- Não é o OpenSddRag. Não chama `mcp__opensddrag__*` em nenhum passo.
