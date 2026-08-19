import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";

const APP_NAME = "Jeff AI";
const APP_DESCRIPTION =
  "Jeff AI is a self-hosted AI assistant. It writes and reviews code, researches information, creates documents and spreadsheets, generates images, and organizes Gmail — synchronizing and sending email only after you connect a Google account via OAuth.";

export const metadata: Metadata = {
  title: APP_NAME,
  applicationName: APP_NAME,
  description: APP_DESCRIPTION,
  openGraph: {
    title: APP_NAME,
    siteName: APP_NAME,
    description: APP_DESCRIPTION,
    locale: "en_US",
    type: "website",
  },
  appleWebApp: {
    title: APP_NAME,
  },
};

/**
 * Dedicated OAuth brand-verification homepage at `/public/about`.
 *
 * Google's automated checker caches a verdict per URL. `/` previously served
 * the login form, so resubmitting the same homepage URL keeps failing even
 * after the marketing landing was deployed. This route is a fresh, public,
 * server-rendered page whose first screen states: the app name, what Jeff AI
 * does, why it requests Google user data, and a Privacy Policy link — the
 * four checks in https://support.google.com/cloud/answer/13807376
 *
 * Point the Cloud Console Branding "Homepage URL" at
 * `https://jeff.conexaoelite.com.br/public/about` after deploy.
 */
export default function AboutPage() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: APP_NAME,
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    description: APP_DESCRIPTION,
  };

  return (
    <main className="min-h-screen bg-background px-6 py-16 text-foreground">
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
      />
      <div className="mx-auto flex max-w-3xl flex-col gap-10">
        <header className="space-y-4">
          <Image
            src="/logo-conexao-elite.png"
            alt={APP_NAME}
            width={80}
            height={80}
            priority
            className="h-20 w-20"
          />
          <h1 className="text-4xl font-semibold tracking-tight">{APP_NAME}</h1>
          <p>
            Jeff AI is a self-hosted artificial intelligence assistant that
            you use in the browser for everyday work: writing and reviewing
            code, researching information, creating documents and
            spreadsheets, generating images, and organizing email.
          </p>
          <p>
            O Jeff AI é um assistente de inteligência artificial
            auto-hospedado que você usa pelo navegador para o trabalho do dia
            a dia: escrever e revisar código, pesquisar, montar documentos e
            planilhas, gerar imagens e organizar e-mails.
          </p>
          <nav
            aria-label="Legal"
            className="flex flex-wrap gap-x-4 gap-y-2 text-sm"
          >
            <Link
              href="/public/privacy"
              className="underline underline-offset-4"
            >
              Privacy Policy
            </Link>
            <Link
              href="/public/privacy"
              className="underline underline-offset-4"
            >
              Política de Privacidade
            </Link>
            <Link
              href="/public/terms"
              className="underline underline-offset-4"
            >
              Terms of Service
            </Link>
            <Link
              href="/public/terms"
              className="underline underline-offset-4"
            >
              Termos de Serviço
            </Link>
          </nav>
        </header>

        <section className="space-y-3">
          <h2 className="text-2xl font-semibold tracking-tight">
            What Jeff AI does
          </h2>
          <p>
            Jeff AI is a self-hosted AI assistant. You describe a task in
            natural language and it executes: editing project files, running
            tests, using git (with your approval before changes), producing
            documents and spreadsheets, generating images, searching the web,
            and managing email. It runs on the operator&apos;s own server, not
            as a third-party SaaS inbox.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-2xl font-semibold tracking-tight">
            O que o Jeff AI faz
          </h2>
          <p>
            O Jeff AI é um assistente de inteligência artificial
            auto-hospedado. Você descreve a tarefa em linguagem natural e ele
            executa: edita arquivos, roda testes, usa git (com a sua
            aprovação antes de alterar qualquer coisa), produz documentos e
            planilhas, gera imagens, pesquisa na web e organiza e-mails. Roda
            no servidor de quem opera a instância.
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-2xl font-semibold tracking-tight">
            Why Jeff AI requests Google user data
          </h2>
          <p>
            If you choose to connect a Gmail account, Jeff AI requests Google
            OAuth access to your mailbox solely to synchronize incoming email
            and to send messages on your behalf, limited to the scopes you
            grant on the consent screen. Access and refresh tokens are stored
            encrypted. You can revoke this access at any time from Jeff AI or
            at{" "}
            <a
              href="https://myaccount.google.com/permissions"
              className="underline underline-offset-4"
              rel="noreferrer"
            >
              myaccount.google.com/permissions
            </a>
            . Full details are in the{" "}
            <Link
              href="/public/privacy"
              className="underline underline-offset-4"
            >
              Privacy Policy
            </Link>
            .
          </p>
        </section>

        <section className="space-y-3">
          <h2 className="text-2xl font-semibold tracking-tight">
            Por que o Jeff AI solicita dados da sua conta Google
          </h2>
          <p>
            Se você conectar uma conta Gmail, o Jeff AI solicita, via OAuth
            do Google, acesso à sua caixa de entrada apenas para sincronizar
            e-mails e enviar mensagens em seu nome, dentro do escopo que você
            autorizar. Os tokens ficam criptografados. Você pode revogar o
            acesso pela interface do Jeff AI ou em{" "}
            <a
              href="https://myaccount.google.com/permissions"
              className="underline underline-offset-4"
              rel="noreferrer"
            >
              myaccount.google.com/permissions
            </a>
            . Detalhes na{" "}
            <Link
              href="/public/privacy"
              className="underline underline-offset-4"
            >
              Política de Privacidade
            </Link>
            .
          </p>
        </section>

        <p>
          <Link
            href="/public/login"
            className="underline underline-offset-4"
          >
            Sign in to Jeff AI
          </Link>
        </p>
      </div>
    </main>
  );
}
