import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

import { Button } from "@/components/ui/button";

export const metadata: Metadata = {
  // Kept as the exact string configured on the Google OAuth consent screen
  // ("Nome do app"), with no suffix, so an exact-match check against the
  // page title cannot fail — the longer explainer lives in `description`
  // instead. See app-branding-consistency REQ-003.
  title: "Jeff AI",
  description:
    "Jeff AI é um assistente de inteligência artificial auto-hospedado para o trabalho do dia a dia: escrever e revisar código, pesquisar, criar documentos e planilhas, e organizar e-mails.",
};

const CAPABILITIES = [
  {
    title: "Escreve e cuida de código",
    body: "Edita arquivos do seu projeto, roda os testes e usa git, sempre pedindo sua aprovação antes de alterar qualquer coisa.",
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
          {/* Mesmo arquivo de logotipo enviado à tela de consentimento OAuth
              do Google. A correspondência visual entre as duas superfícies é
              parte do que a verificação de marca do Google confere. */}
          <Image
            src="/logo-conexao-elite.png"
            alt="Conexão Elite"
            width={80}
            height={80}
            priority
            className="mx-auto h-20 w-20"
          />
          <h1 className="text-4xl font-semibold tracking-tight">Jeff AI</h1>
          <p className="text-sm font-medium text-muted-foreground">
            Um produto da Conexão Elite
          </p>
          <p className="text-lg text-muted-foreground">
            O Jeff AI é um assistente de inteligência artificial
            auto-hospedado, que ajuda você a escrever código, pesquisar,
            produzir documentos e cuidar dos seus e-mails — tudo em uma só
            conversa.
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
            O Jeff AI é um assistente de inteligência artificial que você usa
            pelo navegador para resolver o trabalho do dia a dia: escrever e
            revisar textos e código, pesquisar informações, montar documentos
            e planilhas, gerar imagens e organizar a sua caixa de e-mail.
            Você conversa com ele em português, descrevendo a tarefa, e ele
            executa.
          </p>
          <p className="text-muted-foreground">
            Ele é auto-hospedado: roda em servidor próprio, com modelo de
            linguagem próprio. Por isso as suas conversas, os seus documentos
            e os seus e-mails ficam na infraestrutura de quem opera a
            instância, e não em um serviço de terceiros.
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

        <section className="space-y-4">
          <h2 className="text-2xl font-semibold tracking-tight">
            Acesso à sua conta Google
          </h2>
          <p className="text-muted-foreground">
            Se você conectar uma conta Gmail, o Jeff AI solicita, via OAuth do
            Google, acesso à sua caixa de entrada apenas para sincronizar
            e-mails e enviar mensagens em seu nome, dentro do escopo que você
            autorizar no momento da conexão. Os tokens de acesso ficam
            armazenados de forma criptografada, e você pode revogar esse
            acesso quando quiser — pela própria interface do Jeff AI ou em{" "}
            <a
              href="https://myaccount.google.com/permissions"
              className="underline underline-offset-4"
              rel="noreferrer"
            >
              myaccount.google.com/permissions
            </a>
            . Detalhes completos na{" "}
            <Link
              href="/public/privacy"
              className="underline underline-offset-4"
            >
              Política de Privacidade
            </Link>
            .
          </p>
        </section>

        <section className="space-y-6">
          <h2 className="text-2xl font-semibold tracking-tight">
            Como usar
          </h2>
          <div className="grid gap-4 sm:grid-cols-2">
            {HOW_TO_USE.map((item) => (
              <div
                key={item.step}
                className="space-y-1 rounded-lg border border-border p-4"
              >
                <span className="text-sm font-semibold text-muted-foreground">
                  Passo {item.step}
                </span>
                <h3 className="font-medium">{item.title}</h3>
                <p className="text-sm text-muted-foreground">{item.body}</p>
              </div>
            ))}
          </div>
        </section>

        <nav
          aria-label="Ações"
          className="flex flex-wrap items-center justify-center gap-3"
        >
          <Button asChild>
            <Link href="/public/login">Começar agora</Link>
          </Button>
        </nav>

        <footer className="space-y-3 border-t border-border pt-6 text-center text-sm text-muted-foreground">
          <p>
            O Jeff AI é desenvolvido e operado pela Conexão Elite. Suporte:{" "}
            <a
              href="mailto:suporte@conexaoelite.com"
              className="underline underline-offset-4"
            >
              suporte@conexaoelite.com
            </a>
          </p>
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
