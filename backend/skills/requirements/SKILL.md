---
name: requirements
description: "Use this skill whenever the user asks for a requirements document — vision, use cases, user stories, business rules, stakeholders, constraints — or any multi-section written deliverable that should be planned, generated section by section, and consolidated into one file. Triggers include: 'requisitos', 'caso de uso', 'história de usuário', 'documento de requisitos', 'levantamento de requisitos'. This replaces the fullstack_subagent — no subagent is invoked for this work. For image/banner/illustration requests, do NOT write a document for that part; route it to image_design_subagent instead (it presents a design plan and requires user approval before generating)."
---

# Requisitos — documento de requisitos como skill

## Visão geral

Gerar um documento de requisitos é: planejar as seções, escrever cada seção
como um arquivo próprio, e consolidar tudo num único documento final com
`merge_generated_files`. **Nenhum subagente é invocado** — este é o
substituto direto do `fullstack_subagent`, que fazia o mesmo trabalho isolado
num `SubAgent` dedicado. O conteúdo abaixo vem do prompt dele; o que muda é a
embalagem.

> **Envelope de permissões:** esta skill é conselho ao modelo, nunca concessão
> de acesso. Se `write_file` não estiver no envelope concedido para a tarefa,
> os passos de escrita ficam bloqueados normalmente — a skill não amplia o
> que o agente pode fazer.

## Passo a passo

1. **Analisar o pedido** e identificar as seções necessárias (ex.: visão,
   casos de uso, histórias de usuário, regras de negócio, stakeholders,
   restrições). Nem todo pedido precisa de todas — só as seções pedidas ou
   claramente implícitas.
2. **Planejar** as seções antes de escrever qualquer conteúdo.
3. **Gerar cada seção** com `write_file`, um arquivo por seção, no diretório
   de saída (`backend/outputs/`). Use `get_date_time_current` para preencher
   datas no conteúdo. Use `ls`/`read_file` no diretório de saída para
   verificar o que já existe antes de sobrescrever.
4. **Consolidar** com `merge_generated_files(output_dir, final_filename)` —
   ela ordena as seções por nome de arquivo e concatena na ordem, formando o
   documento final. Não concatene seções manualmente; é para isso que a tool
   existe (evita sobrecarregar a memória do modelo com o texto inteiro de
   cada seção).
5. **Entregar** o documento final em `backend/outputs/` (ex.:
   `documento_final.md`).

## Fora de escopo — não é responsabilidade desta skill

Esta skill NÃO gera imagens e não tem ferramenta para isso. Se o pedido
envolver imagem, banner, ilustração ou design visual:
- **Pedido puramente de imagem:** não escreva documento nenhum; a tarefa deve
  ir para `image_design_subagent` (que apresenta um plano de design e exige
  aprovação do usuário antes de gerar).
- **Pedido híbrido (documento + imagem):** escreva normalmente a parte de
  documento e, ao final, sinalize claramente qual parte é de imagem para ser
  delegada a `image_design_subagent`. Nunca tente gerar a imagem você mesmo.

Esta skill também NÃO implementa código de aplicação — o foco é requisitos,
não implementação.
