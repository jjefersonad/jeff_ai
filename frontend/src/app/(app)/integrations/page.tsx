"use client";

/**
 * Minimal "Integrações" screen (whatsapp-evolution-channel-task-frontend-1,
 * telegram-integration-frontend-registration).
 *
 * Lets an authenticated user request a WhatsApp or Telegram link code
 * (`POST /api/integrations/{whatsapp,telegram}/link-code`) and see the code
 * plus its expiration without calling the API manually. The user then sends
 * that code as the first WhatsApp message, or as `/start <código>` to the
 * Telegram bot, to complete the link.
 */

import { useCallback, useState } from "react";
import { MessageCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { LinkCodeCard } from "@/components/integrations/link-code-card";
import { ApiError } from "@/lib/api";
import {
  createTelegramLinkCode,
  createWhatsAppLinkCode,
  type TelegramLinkCode,
  type WhatsAppLinkCode,
} from "@/lib/integrations";

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

  const [telegramLinkCode, setTelegramLinkCode] = useState<TelegramLinkCode | null>(
    null
  );
  const [telegramLoading, setTelegramLoading] = useState(false);
  const [telegramError, setTelegramError] = useState<string | null>(null);

  const handleGenerateTelegram = useCallback(async () => {
    setTelegramLoading(true);
    setTelegramError(null);
    try {
      const result = await createTelegramLinkCode();
      setTelegramLinkCode(result);
    } catch (err) {
      setTelegramLinkCode(null);
      setTelegramError(
        err instanceof ApiError ? err.message : "Falha ao gerar código de vínculo"
      );
    } finally {
      setTelegramLoading(false);
    }
  }, []);

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
            <LinkCodeCard code={linkCode.code} expiresAt={linkCode.expires_at} />
          )}
        </section>

        <section className="rounded-md border border-border bg-card p-4">
          <h2 className="font-medium">Telegram</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Gere um código de vínculo e envie-o como <code>/start &lt;código&gt;</code>{" "}
            para o bot da Jeff AI no Telegram para conectar sua conta.
          </p>

          <Button
            className="mt-4"
            onClick={handleGenerateTelegram}
            disabled={telegramLoading}
          >
            {telegramLoading ? "Gerando..." : "Gerar código de vínculo"}
          </Button>

          {telegramError && (
            <p className="mt-3 text-sm text-destructive" role="alert">
              {telegramError}
            </p>
          )}

          {telegramLinkCode && (
            <LinkCodeCard
              code={telegramLinkCode.code}
              expiresAt={telegramLinkCode.expires_at}
            />
          )}
        </section>
      </main>
    </div>
  );
}
