# Guia de Divulgação do Jeff AI (LinkedIn & Instagram)

> **Isto é documentação estática do projeto**, para o mantenedor divulgar o Jeff AI nas redes sociais — não é uma feature do produto. Não confundir com a capacidade `marketing-copy-generation` do próprio Jeff AI, que gera copy de marketing para os *usuários finais* do assistente sobre os produtos *deles*. Este guia não usa nenhuma tool ou skill do agente; é só markdown para copiar/adaptar manualmente.

## Tom e estrutura por plataforma

### LinkedIn

- **Tom:** profissional, foco técnico/produto. Fale de arquitetura, decisões de design e capacidades reais — o público é de desenvolvedores e tomadores de decisão técnica.
- **Estrutura de post:**
  1. Gancho de 1-2 linhas com o problema ou a novidade.
  2. Contexto curto (por que isso importa).
  3. 2-4 bullets com detalhes concretos (o que foi construído, como funciona).
  4. Chamada para ação: link para o repositório, convite para feedback ou pergunta para gerar comentários.
- **Chamada para ação:** convide para ver o código, abrir uma issue ou comentar com um caso de uso.

### Instagram

- **Tom:** mais visual e casual. Prioriza o "ver funcionando" sobre a explicação técnica detalhada.
- **Estrutura de post:**
  1. Legenda curta, direta, com emoji opcional no início.
  2. 1-2 frases sobre o que a imagem/vídeo mostra.
  3. Hashtags relevantes no fim (ex.: `#IA #opensource #devtools`).
- **Chamada para ação:** "salve para depois", "comente sua opinião", ou link na bio.

## Templates

Os templates usam placeholders genéricos (`[nome da feature]`, `[breve descrição]`) — adapte para a capacidade real que você está divulgando. Não referencie uma feature específica diretamente no template para que ele continue reutilizável conforme o projeto evolui.

### 1. Anúncio de lançamento

**LinkedIn:**
> 🚀 Lançamos o Jeff AI: um assistente de IA self-hosted que roda no seu próprio modelo (Ollama).
>
> A ideia: um Claude que você possui, que você usa para tudo — código, pesquisa, marketing — e que melhora a si mesmo.
>
> O que já funciona:
> • Skills dinâmicas, criadas e instaladas em runtime
> • Memória própria e persistente
> • Geração de imagens e documentos Office
>
> Curioso para ver como? [link do repositório]

**Instagram:**
> 🤖 Conheça o Jeff AI — sua IA, seu modelo, suas regras.
>
> Self-hosted, memória própria, e capaz de aprender novas skills sozinho.
>
> Link na bio 🔗
>
> #IA #opensource #devtools #selfhosted

### 2. Atualização de funcionalidade

**LinkedIn:**
> Nova capacidade no Jeff AI: [nome da feature].
>
> [breve descrição do que ela resolve e como funciona, 2-3 frases]
>
> Isso foi possível graças a [decisão técnica ou arquitetura relevante].
>
> Exemplo real já implementado: a geração de imagens passa por um plano de design com **aprovação obrigatória do usuário** antes de qualquer chamada ao Gemini — nada é gerado sem revisão explícita.
>
> Feedback e sugestões são bem-vindos nos comentários.

**Instagram:**
> ✨ Novidade no Jeff AI: [nome da feature]!
>
> [1 frase sobre o benefício prático]
>
> Testou? Conta pra gente nos comentários 👇
>
> #devtools #IA #buildinpublic

### 3. Bastidores de desenvolvimento

**LinkedIn:**
> Bastidores do Jeff AI: como decidimos [decisão de arquitetura ou trade-off].
>
> O desafio: [problema enfrentado]
> A decisão: [o que foi escolhido e por quê]
> O que ficou de fora (por enquanto): [non-goal ou dívida técnica conhecida]
>
> Construir em público significa mostrar também o que ainda não está pronto.

**Instagram:**
> 🛠️ Nos bastidores do Jeff AI: [breve descrição do que está sendo construído agora].
>
> Ainda em progresso, mas já dá pra ver a direção 👀
>
> #buildinpublic #IA #devlife

## Assets visuais

Sem material visual pronto? O próprio projeto rodando é a fonte mais rápida:

- **Screenshot da aplicação:** suba a stack (`docker compose up -d` ou `yarn dev` no frontend) e capture a tela em [http://localhost:3000](http://localhost:3000) — mostra a interface de conversa real, sem precisar de mockups.
- **Diagrama de arquitetura:** use a skill `diagram-creator` (Mermaid/PlantUML) para gerar um diagrama simples da arquitetura descrita em [CLAUDE.md](../CLAUDE.md) ou [docs/ARCHITECTURE.md](ARCHITECTURE.md) — bom para posts de bastidores ou de lançamento.
- **GIF de uso:** grave a tela durante um fluxo curto (ex.: pedir uma skill nova, gerar uma imagem com aprovação) usando qualquer gravador de tela; GIFs curtos (5-10s) funcionam melhor no Instagram do que vídeos longos.
