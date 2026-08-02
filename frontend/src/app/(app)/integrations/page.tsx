"use client";

/**
 * Minimal "Integrações" screen (whatsapp-evolution-channel-task-frontend-1).
 *
 * Lets an authenticated user request a WhatsApp link code
 * (`POST /api/integrations/whatsapp/link-code`, whatsapp-channel REQ-001)
 * and see the code plus its expiration without calling the API manually.
 * The user then sends that code as the first WhatsApp message to Jeff AI's
 * central number to complete the link.
 */

import { useCallback, useState } from "react";
import { MessageCircle, Copy } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { createWhatsAppLinkCode, type WhatsAppLinkCode } from "@/lib/integrations";

export default function IntegrationsPage() {
  const [linkCode, setLinkCode] = useState<WhatsAppLinkCode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await createWhatsAppLinkCode();
      setLinkCode(result);
    } catch (err) {
      setLinkCode(null);
      setError(
        err instanceof ApiError ? err.message : "Falha ao gerar código de vínculo"
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const handleCopy = useCallback(() => {
    if (!linkCode) return;
    navigator.clipboard.writeText(linkCode.code);
    toast.success("Código copiado");
  }, [linkCode]);

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[720px] items-center gap-3 px-6 py-4">
          <MessageCircle size={24} className="text-primary" aria-hidden="true" />
          <h1 className="text-xl font-semibold">Integrações</h1>
        </div>
      </header>

      <main className="mx-auto flex max-w-[720px] flex-col gap-6 px-6 py-8">
        <section className="rounded-md border border-border bg-card p-4">
          <h2 className="font-medium">WhatsApp</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Gere um código de vínculo e envie-o como primeira mensagem para o
            número da Jeff AI no WhatsApp para conectar sua conta.
          </p>

          <Button className="mt-4" onClick={handleGenerate} disabled={loading}>
            {loading ? "Gerando..." : "Gerar código de vínculo"}
          </Button>

          {error && (
            <p className="mt-3 text-sm text-destructive" role="alert">
              {error}
            </p>
          )}

          {linkCode && (
            <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-border bg-background p-3">
              <div>
                <p className="font-mono text-lg font-semibold tracking-wide">
                  {linkCode.code}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Expira em {new Date(linkCode.expires_at).toLocaleString()}
                </p>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={handleCopy}
                aria-label="Copiar código"
              >
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
          )}
        </section>
      </main>
    </div>
  );
}
