import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  // Kept as the exact string configured on the Google OAuth consent screen
  // ("Nome do app"), with no suffix, so an exact-match check against the
  // page title cannot fail — the longer explainer lives in `description`
  // instead. See app-branding-consistency REQ-003.
  title: "Jeff AI",
  description:
    "Jeff AI é um assistente de inteligência artificial auto-hospedado: roda no seu próprio modelo, faz o que o Claude Code faz, e serve qualquer tarefa — código, pesquisa, marketing, documentos.",
};

const CAPABILITIES = [
  {
    title: "Escreve e cuida de código",
    body: "Edita arquivos, roda testes, usa git — as mesmas funções do Claude Code, no seu próprio modelo.",
  },
  {
    title: "Serve qualquer tarefa",
    body: "Campanhas de marketing, pesquisa, documentos, planilhas, imagens — não existe uma lista fixa de casos de uso.",
  },
  {
    title: "Cria habilidades novas",
    body: "Quando falta uma capacidade, ele monta uma skill nova para resolver, em vez de ficar limitado ao que já existe.",
  },
  {
    title: "Conecta com suas ferramentas",
    body: "Você pluga os servidores MCP que quiser, e ele passa a usá-los como mais uma ferramenta disponível.",
  },
  {
    title: "Planeja e executa em etapas",
    body: "Para tarefas maiores, ele monta um plano, mostra as etapas sensíveis para você aprovar, e executa o resto.",
  },
  {
    title: "Lembra do que já foi feito",
    body: "Mantém memória própria e persistente — conversas e decisões anteriores continuam disponíveis depois.",
  },
];

const HOW_TO_USE = [
  {
    step: "1",
    title: "Entre com sua conta",
    body: "Acesse com as credenciais da sua instância Jeff AI.",
  },
  {
    step: "2",
    title: "Descreva a tarefa",
    body: "Peça em linguagem natural o que você precisa — não é preciso comando especial.",
  },
  {
    step: "3",
    title: "Acompanhe e aprove",
    body: "Para ações mais sensíveis (editar código, enviar algo, rodar um comando), ele pausa e pede sua aprovação antes de seguir.",
  },
  {
    step: "4",
    title: "Receba o resultado",
    body: "O trabalho fica registrado na conversa, e o que for relevante entra na memória para as próximas vezes.",
  },
];

/**
 * Public marketing landing page at `/public/landing`.
 *
 * Static Server Component — no session query, no backend endpoint, no
 * interactivity required. Reached directly at `/public/landing` (it lives
 * under `/public/*`, which `isPublicPath()` in `src/middleware.ts` already
 * treats as public) and also at `/` for unauthenticated requests, via the
 * rewrite in `src/middleware.ts`, so crawlers — including Google's OAuth
 * brand verification crawler — get a 200 with real content instead of a
 * redirect to `/public/login`.
 *
 * "Jeff AI" is used verbatim throughout (title, hero, capabilities, CTA),
 * matching the app name configured on the Google OAuth consent screen and
 * the name shown on the privacy and terms pages.
 */
export default function LandingPage() {
  return (
    <main className="min-h-screen bg-background px-6 py-16 text-foreground">
      <div className="mx-auto flex max-w-3xl flex-col gap-16">
        <header className="space-y-4 text-center">
          <h1 className="text-4xl font-semibold tracking-tight">Jeff AI</h1>
          <p className="text-lg text-muted-foreground">
            Um assistente de inteligência artificial auto-hospedado — que
            roda no seu próprio modelo, sob seu próprio controle, e que você
            usa para qualquer tarefa.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
            <Button asChild>
              <Link href="/public/login">Entrar</Link>
            </Button>
          </div>
        </header>

        <section className="space-y-4">
          <h2 className="text-2xl font-semibold tracking-tight">
            O que é o Jeff AI
          </h2>
          <p className="text-muted-foreground">
            O Jeff AI é um Claude que você hospeda na sua própria
            infraestrutura, rodando no seu próprio modelo (Ollama). Ele faz o
            mesmo que o Claude Code faz — escreve e revisa código, roda
            testes, usa git — e também cuida de qualquer outra tarefa que
            você precisar, sem depender de um serviço externo para
            funcionar.
          </p>
          <p className="text-muted-foreground">
            Como ele roda no seu próprio modelo, os seus dados e as suas
            conversas permanecem na sua instância.
          </p>
        </section>

        <section className="space-y-6">
          <h2 className="text-2xl font-semibold tracking-tight">
            O que você pode fazer com ele
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {CAPABILITIES.map((capability) => (
              <div
                key={capability.title}
                className="space-y-1 rounded-lg border border-border p-4"
              >
                <h3 className="font-medium">{capability.title}</h3>
                <p className="text-sm text-muted-foreground">
                  {capability.body}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="space-y-6">
          <h2 className="text-2xl font-semibold tracking-tight">
            Como usar
          </h2>
          <ol className="grid gap-4 sm:grid-cols-2">
            {HOW_TO_USE.map((item) => (
              <li
                key={item.step}
                className="space-y-1 rounded-lg border border-border p-4"
              >
                <span className="text-sm font-semibold text-muted-foreground">
                  Passo {item.step}
                </span>
                <h3 className="font-medium">{item.title}</h3>
                <p className="text-sm text-muted-foreground">{item.body}</p>
              </li>
            ))}
          </ol>
        </section>

        <nav
          aria-label="Ações"
          className="flex flex-wrap items-center justify-center gap-3"
        >
          <Button asChild>
            <Link href="/public/login">Começar agora</Link>
          </Button>
        </nav>

        <footer className="border-t border-border pt-6 text-center text-sm text-muted-foreground">
          <nav
            aria-label="Documentos legais"
            className="flex flex-wrap justify-center gap-x-4 gap-y-2"
          >
            <Link
              href="/public/privacy"
              className="underline-offset-4 hover:text-foreground hover:underline"
            >
              Política de Privacidade
            </Link>
            <Link
              href="/public/terms"
              className="underline-offset-4 hover:text-foreground hover:underline"
            >
              Termos de Serviço
            </Link>
          </nav>
        </footer>
      </div>
    </main>
  );
}
