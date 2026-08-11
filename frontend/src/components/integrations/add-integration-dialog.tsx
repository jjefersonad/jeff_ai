"use client";

import { useCallback, useEffect, useState } from "react";
import { MessageCircle, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { LinkCodeCard } from "@/components/integrations/link-code-card";
import { ApiError } from "@/lib/api";
import {
  buildDeepLinkHref,
  ChannelLinkConfig,
  createTelegramLinkCode,
  createWhatsAppLinkCode,
  getChannelLinkConfig,
} from "@/lib/integrations";

type PickedType = "whatsapp" | "telegram";

const FLOW_COPY: Record<PickedType, { label: string; instruction: React.ReactNode }> = {
  whatsapp: {
    label: "WhatsApp",
    instruction:
      "Gere um código de vínculo e envie-o como primeira mensagem para o número da Jeff AI no WhatsApp para conectar sua conta.",
  },
  telegram: {
    label: "Telegram",
    instruction: (
      <>
        Gere um código de vínculo e envie-o como <code>/start &lt;código&gt;</code> para
        o bot da Jeff AI no Telegram para conectar sua conta.
      </>
    ),
  },
};

export interface AddIntegrationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called when the dialog closes, so the caller can refresh the integrations list. */
  onLinked?: () => void;
}

/**
 * "Adicionar integração" modal (design D6' of `user-integrations-list-delete`):
 * a type picker (WhatsApp/Telegram) that reveals the existing generate-code
 * flow for the picked type, reusing `createWhatsAppLinkCode()`,
 * `createTelegramLinkCode()`, and `LinkCodeCard` unchanged.
 */
export function AddIntegrationDialog({
  open,
  onOpenChange,
  onLinked,
}: AddIntegrationDialogProps) {
  const [pickedType, setPickedType] = useState<PickedType | null>(null);
  const [flowLoading, setFlowLoading] = useState(false);
  const [flowError, setFlowError] = useState<string | null>(null);
  const [flowLinkCode, setFlowLinkCode] = useState<{
    code: string;
    expires_at: string;
  } | null>(null);
  const [channelLinkConfig, setChannelLinkConfig] = useState<ChannelLinkConfig | null>(null);

  // Fetch config once per mount (channel-link-wiring design Decision 5)
  useEffect(() => {
    getChannelLinkConfig()
      .then(setChannelLinkConfig)
      .catch(() => {
        // Non-blocking: config fetch failure degrades gracefully (no deep link)
        setChannelLinkConfig(null);
      });
  }, []);

  useEffect(() => {
    if (open) {
      setPickedType(null);
      setFlowLoading(false);
      setFlowError(null);
      setFlowLinkCode(null);
    }
  }, [open]);

  const handlePick = useCallback((type: PickedType) => {
    setPickedType(type);
    setFlowError(null);
    setFlowLinkCode(null);
  }, []);

  const handleGenerate = useCallback(async () => {
    if (!pickedType) return;
    setFlowLoading(true);
    setFlowError(null);
    try {
      const result =
        pickedType === "whatsapp"
          ? await createWhatsAppLinkCode()
          : await createTelegramLinkCode();
      setFlowLinkCode(result);
    } catch (err) {
      setFlowError(
        err instanceof ApiError ? err.message : "Falha ao gerar código de vínculo"
      );
    } finally {
      setFlowLoading(false);
    }
  }, [pickedType]);

  const handleOpenChange = useCallback(
    (next: boolean) => {
      onOpenChange(next);
      if (!next) onLinked?.();
    },
    [onOpenChange, onLinked]
  );

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Adicionar integração</DialogTitle>
          {!pickedType && (
            <DialogDescription>
              Escolha qual integração você deseja adicionar.
            </DialogDescription>
          )}
        </DialogHeader>

        {!pickedType && (
          <div className="grid grid-cols-2 gap-3">
            <button
              type="button"
              onClick={() => handlePick("whatsapp")}
              className="flex flex-col items-center gap-2 rounded-md border border-border p-4 text-sm hover:bg-accent"
            >
              <MessageCircle className="h-6 w-6" />
              WhatsApp
            </button>
            <button
              type="button"
              onClick={() => handlePick("telegram")}
              className="flex flex-col items-center gap-2 rounded-md border border-border p-4 text-sm hover:bg-accent"
            >
              <Send className="h-6 w-6" />
              Telegram
            </button>
          </div>
        )}

        {pickedType && (
          <div>
            <p className="text-sm text-muted-foreground">
              {FLOW_COPY[pickedType].instruction}
            </p>

            <Button className="mt-4" onClick={handleGenerate} disabled={flowLoading}>
              {flowLoading ? "Gerando..." : "Gerar código de vínculo"}
            </Button>

            {flowError && (
              <p className="mt-3 text-sm text-destructive" role="alert">
                {flowError}
              </p>
            )}

            {flowLinkCode && (
              <LinkCodeCard
                code={flowLinkCode.code}
                expiresAt={flowLinkCode.expires_at}
                deepLinkHref={
                  pickedType && channelLinkConfig
                    ? buildDeepLinkHref(pickedType, flowLinkCode.code, channelLinkConfig)
                    : undefined
                }
              />
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
