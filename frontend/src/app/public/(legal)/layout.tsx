import Link from "next/link";
import type { ReactNode } from "react";

/**
 * Shared chrome for `/public/privacy` and `/public/terms`.
 *
 * The `(legal)` route group does not appear in the URL, so these pages stay
 * at `/public/privacy` and `/public/terms`. Login lives at
 * `frontend/src/app/public/login/page.tsx` and is not wrapped by this layout
 * — there is no `frontend/src/app/public/layout.tsx`.
 *
 * This layout does not import `NavSidebar` or `UserMenu`. Those belong to
 * the authenticated `(app)` shell.
 */
export default function LegalLayout({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-background px-6 py-10">
      <div className="mx-auto flex min-h-[calc(100vh-5rem)] max-w-2xl flex-col">
        <div className="flex-1">{children}</div>
        <footer className="mt-12 border-t border-border pt-6 text-sm text-muted-foreground">
          <nav
            aria-label="Documentos legais"
            className="flex flex-wrap gap-x-4 gap-y-2"
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
            <Link
              href="/public/login"
              className="underline-offset-4 hover:text-foreground hover:underline"
            >
              Entrar
            </Link>
          </nav>
        </footer>
      </div>
    </div>
  );
}
