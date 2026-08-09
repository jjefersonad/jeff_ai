"use client";

import { useCallback } from "react";
import { Copy } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

export interface LinkCodeCardProps {
  code: string;
  expiresAt: string;
  onCopy?: () => void;
}

/**
 * Displays a generated link code (WhatsApp, Telegram, ...) with its expiry
 * and a copy-to-clipboard control. Shared between integration sections so
 * the code-card layout stays in one place (design D2 of
 * telegram-integration-frontend-registration).
 */
export function LinkCodeCard({ code, expiresAt, onCopy }: LinkCodeCardProps) {
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code);
    toast.success("Código copiado");
    onCopy?.();
  }, [code, onCopy]);

  return (
    <div className="mt-4 flex items-center justify-between gap-3 rounded-md border border-border bg-background p-3">
      <div>
        <p className="font-mono text-lg font-semibold tracking-wide">{code}</p>
        <p className="mt-1 text-xs text-muted-foreground">
          Expira em {new Date(expiresAt).toLocaleString()}
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
  );
}
