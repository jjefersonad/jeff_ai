import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Termos de Serviço — Jeff AI",
};

const EFFECTIVE_DATE = "2026-08-13";

/**
 * Public Terms of Service at `/public/terms`.
 *
 * Static Server Component — no session query, no backend endpoint.
 * Describes Jeff AI as a self-hosted assistant; third-party connections
 * (including Gmail) are optional and under the user's control.
 */
export default function TermsPage() {
  return (
    <article
      lang="pt-BR"
      className="space-y-8 text-foreground"
    >
      <header className="space-y-2">
        <h1 className="text-3xl font-semibold tracking-tight">
          Termos de Serviço
        </h1>
        <p className="text-sm text-muted-foreground">
          Vigência:{" "}
          <time dateTime={EFFECTIVE_DATE}>13 de agosto de 2026</time>
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Descrição do serviço</h2>
        <p>
          O Jeff AI é um assistente de inteligência artificial auto-hospedado:
          o software roda na infraestrutura do operador da instância. Ele
          permite conversar com um modelo de linguagem, gerar documentos e
          imagens, e conectar ferramentas e contas que o usuário ou o
          administrador configurarem.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Uso aceitável</h2>
        <p>
          O usuário deve usar a instância de forma lícita, respeitando estes
          termos, a legislação aplicável e as políticas das contas de
          terceiros que conectar. É vedado tentar burlar controles de acesso,
          explorar a instância para atacar outros sistemas, ou usar o
          assistente para atividade ilegal.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Limitação de responsabilidade</h2>
        <p>
          O Jeff AI gera conteúdo por modelo de linguagem e pode errar. O
          operador e o software são oferecidos como estão, sem garantia de
          acurácia, disponibilidade contínua ou adequação a um fim específico.
          O usuário é responsável por revisar saídas antes de usá-las em
          decisões ou comunicações.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Contas de terceiros</h2>
        <p>
          Conectar contas de terceiros — inclusive Gmail via OAuth — é
          opcional e permanece sob controle do usuário. O usuário pode
          recusar o consentimento, desconectar a conta na interface do Jeff
          AI e revogar o acesso no provedor (por exemplo, nas permissões da
          conta Google). O uso dessas contas também se sujeita aos termos do
          respectivo provedor.
        </p>
      </section>
    </article>
  );
}
