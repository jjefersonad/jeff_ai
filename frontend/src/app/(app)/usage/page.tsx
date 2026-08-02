"use client";

/**
 * Admin-only token usage report by period.
 *
 * REQ-002: period picker (`from` / `to`) drives `GET /api/usage`.
 * REQ-001: renders prompt / completion / total tokens from the response.
 * REQ-006: non-admin users are redirected away; nav entry is admin-only.
 */

import { FormEvent, useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BarChart3 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";
import { fetchUsage, type UsageTotals } from "@/lib/usage";
import { useAuth } from "@/providers/AuthProvider";

function toDateInputValue(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function defaultFrom(): string {
  const d = new Date();
  d.setDate(d.getDate() - 30);
  return toDateInputValue(d);
}

function defaultTo(): string {
  return toDateInputValue(new Date());
}

/** Convert a YYYY-MM-DD date input to an ISO-ish bound for the API. */
function dayStartIso(date: string): string {
  return `${date}T00:00:00`;
}

function dayEndIso(date: string): string {
  return `${date}T23:59:59`;
}

export default function UsagePage() {
  const router = useRouter();
  const { user } = useAuth();

  const [from, setFrom] = useState(defaultFrom);
  const [to, setTo] = useState(defaultTo);
  const [totals, setTotals] = useState<UsageTotals | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // REQ-006: block non-admin direct URL access once role is known.
  useEffect(() => {
    if (user && user.role !== "admin") {
      router.replace("/");
    }
  }, [user, router]);

  const loadUsage = useCallback(async (fromDate: string, toDate: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchUsage({
        from: dayStartIso(fromDate),
        to: dayEndIso(toDate),
      });
      setTotals(data);
    } catch (err) {
      setTotals(null);
      if (err instanceof ApiError && err.status === 403) {
        setError("Acesso negado. Somente administradores podem ver o consumo.");
        router.replace("/");
        return;
      }
      setError(err instanceof Error ? err.message : "Falha ao carregar consumo");
    } finally {
      setLoading(false);
    }
  }, [router]);

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void loadUsage(from, to);
  };

  if (user && user.role !== "admin") {
    return null;
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-40 border-b border-border bg-background/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-[960px] items-center gap-3 px-6 py-4">
          <BarChart3 size={24} className="text-primary" aria-hidden="true" />
          <h1 className="text-xl font-semibold">Consumo de tokens</h1>
        </div>
      </header>

      <main className="mx-auto flex max-w-[960px] flex-col gap-8 px-6 py-8">
        <form
          onSubmit={onSubmit}
          className="flex flex-col gap-4 sm:flex-row sm:items-end"
          aria-label="Filtro de período"
        >
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="usage-from">De</Label>
            <Input
              id="usage-from"
              type="date"
              value={from}
              onChange={(e) => setFrom(e.target.value)}
              required
            />
          </div>
          <div className="flex flex-1 flex-col gap-2">
            <Label htmlFor="usage-to">Até</Label>
            <Input
              id="usage-to"
              type="date"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              required
            />
          </div>
          <Button type="submit" disabled={loading}>
            Consultar
          </Button>
        </form>

        {error && (
          <p className="text-sm text-destructive" role="alert">
            {error}
          </p>
        )}

        {loading && (
          <div className="grid gap-4 sm:grid-cols-3" aria-busy="true">
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
            <Skeleton className="h-24" />
          </div>
        )}

        {!loading && totals && (
          <section aria-label="Totais de consumo" className="grid gap-4 sm:grid-cols-3">
            <UsageStat label="Prompt tokens" value={totals.prompt_tokens} />
            <UsageStat
              label="Completion tokens"
              value={totals.completion_tokens}
            />
            <UsageStat label="Total tokens" value={totals.total_tokens} />
          </section>
        )}
      </main>
    </div>
  );
}

function UsageStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border border-border bg-card p-4">
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
    </div>
  );
}
