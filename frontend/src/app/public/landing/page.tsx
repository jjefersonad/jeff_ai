import type { Metadata } from "next";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  title: "Jeff AI — assistente de IA auto-hospedado",
  description:
    "Jeff AI é um assistente de inteligência artificial auto-hospedado, que roda no seu próprio modelo, para qualquer tarefa.",
};

/**
 * Public marketing landing page at `/public/landing`.
 *
 * Static Server Component — no session query, no backend endpoint, no
 * interactivity required. Reached directly at `/public/landing` (it lives
 * under `/public/*`, which `isPublicPath()` in `src/middleware.ts` already
 * treats as public) and, once the middleware rewrite from design D1
 * lands, also at `/` for unauthenticated requests so crawlers — including
 * Google's OAuth brand verification crawler — get a 200 with real content
 * instead of a redirect to `/public/login`. The rewrite itself is owned by
 * `google-oauth-verification-brand-fix-task-middleware-1`, not here.
 *
 * "Jeff AI" is used verbatim throughout, matching the app name already set
 * on the Google OAuth consent screen and the name shown on the privacy and
 * terms pages (Design D4 / app-branding-consistency REQ-002).
 */
export default function LandingPage() {
  return (
    <main className="min-h-screen bg-background px-6 py-16 text-foreground">
      <div className="mx-auto flex max-w-2xl flex-col gap-10">
        <header className="space-y-4 text-center">
          <h1 className="text-4xl font-semibold tracking-tight">Jeff AI</h1>
          <p className="text-lg text-muted-foreground">
            Um assistente de inteligência artificial auto-hospedado — que
            roda no seu próprio modelo, sob seu próprio controle.
          </p>
        </header>

        <section className="space-y-4">
          <p>
            O Jeff AI é o seu próprio Claude: um assistente de IA que você
            hospeda na sua infraestrutura, e que usa para qualquer tarefa —
            escrever e revisar código, pesquisar, organizar campanhas de
            marketing, gerar documentos e imagens, ou conversar sobre o que
            for preciso. Não existe uma lista fixa de casos de uso: novas
            capacidades são adicionadas sob demanda, sem depender de nenhum
            serviço externo para funcionar.
          </p>
          <p>
            Como ele roda no seu próprio modelo de linguagem, os seus dados e
            as suas conversas permanecem na sua instância. O assistente
            também mantém memória própria e persistente do que já foi feito,
            e é capaz de ler seu próprio código para melhorar continuamente.
          </p>
        </section>

        <nav
          aria-label="Ações"
          className="flex flex-wrap items-center justify-center gap-3"
        >
          <Button asChild>
            <Link href="/public/login">Entrar</Link>
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
