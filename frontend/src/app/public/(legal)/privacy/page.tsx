import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Política de Privacidade — Jeff AI",
};

const EFFECTIVE_DATE = "2026-08-13";

/**
 * Public Privacy Policy at `/public/privacy`.
 *
 * Static Server Component — no session query, no backend endpoint.
 * Describes the self-hosted Jeff AI instance as it actually behaves
 * (httpOnly session cookie, Fernet-encrypted Gmail OAuth tokens,
 * Postgres memory, documents on disk). The instance operator is the
 * LGPD controller; this page does not invent a central SaaS DPO email.
 */
export default function PrivacyPage() {
  return (
    <article
      lang="pt-BR"
      className="space-y-8 text-foreground"
    >
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">
          Política de Privacidade
        </h1>
        <p className="text-sm text-muted-foreground">
          Vigência:{" "}
          <time dateTime={EFFECTIVE_DATE}>13 de agosto de 2026</time>
        </p>
      </header>

      <p className="text-muted-foreground">
        O Jeff AI é um assistente de inteligência artificial auto-hospedado.
        Esta política descreve como <strong>esta instância</strong> trata
        dados pessoais. O controlador, nos termos da Lei Geral de Proteção
        de Dados (LGPD), é o administrador que opera a instância — não um
        serviço SaaS central.
      </p>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Dados coletados</h2>
        <p>
          A instância pode armazenar: credenciais da conta Jeff AI (nome de
          usuário e senha); o cookie de sessão httpOnly usado para autenticar
          o navegador; memória de longo prazo no banco Postgres; documentos e
          imagens gerados; mensagens de chat; e, se o usuário conectar uma
          caixa de e-mail, metadados e conteúdo de correio necessários para
          sincronizar e enviar mensagens.
        </p>
        <p>
          Se o usuário conectar uma conta Gmail via OAuth, a instância recebe
          tokens de acesso e de atualização (refresh). Esses tokens são
          armazenados de forma criptografada (Fernet) na tabela de
          integrações do usuário. Com eles, o sistema pode sincronizar a
          caixa de entrada e enviar e-mail em nome do usuário, no escopo
          autorizado no consentimento do Google.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Finalidade</h2>
        <p>
          Os dados são tratados para autenticar o usuário, manter o histórico
          de conversas e a memória do assistente, gerar e servir documentos,
          e — quando o usuário autorizar — ler e enviar e-mail. Não usamos
          esses dados para publicidade.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Retenção</h2>
        <p>
          A sessão permanece enquanto o cookie for válido ou até o logout.
          Memória, documentos e e-mails sincronizados permanecem na instância
          até o administrador ou o próprio usuário os excluírem. Tokens
          Gmail permanecem enquanto a conta estiver conectada.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Compartilhamento</h2>
        <p>
          Esta instância não vende dados pessoais. Dados só saem do servidor
          para os serviços que o administrador configurar (por exemplo modelo
          de linguagem, Google OAuth/Gmail, ou buscas na web). Não há
          compartilhamento com terceiros além desses processadores escolhidos
          pelo operador.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Direitos do titular (LGPD)</h2>
        <p>
          O titular pode solicitar confirmação de tratamento, acesso,
          correção, anonimização, portabilidade, informação sobre
          compartilhamentos e revogação de consentimento. Esses pedidos
          devem ser feitos ao administrador desta instância.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Exclusão e revogação</h2>
        <p>
          Para revogar o acesso Gmail: desconecte a conta na interface do
          Jeff AI e revogue o aplicativo em{" "}
          <a
            href="https://myaccount.google.com/permissions"
            className="underline underline-offset-4"
            rel="noreferrer"
          >
            myaccount.google.com/permissions
          </a>
          . Para excluir demais dados (conta, memória, documentos), solicite
          ao administrador da instância. O logout encerra a sessão atual.
        </p>
      </section>
    </article>
  );
}
