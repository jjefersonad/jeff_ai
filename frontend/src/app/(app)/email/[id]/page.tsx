"use client";

/**
 * Dedicated reading route `/email/[id]` (email-detail-full-page REQ-017 / REQ-009).
 *
 * Client page: reads `id` from the route, loads the message with `getEmail`,
 * loads accounts for reply/forward compose, and renders `EmailReadView`.
 * `listHref` is built from `folder` / `account` / `q` so Back restores the
 * inbox list context. `ApiError` (and any other fetch failure) yields the
 * empty/error state with no message body. This is a page, not a detail Dialog.
 */

import { Suspense, useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";

import {
  getEmail,
  listEmailAccounts,
  type Email,
  type EmailAccount,
} from "@/lib/email";

import { EmailReadView } from "../EmailReadView";

const LIST_QUERY_KEYS = ["folder", "account", "q"] as const;

function buildListHref(searchParams: URLSearchParams): string {
  const next = new URLSearchParams();
  for (const key of LIST_QUERY_KEYS) {
    const value = searchParams.get(key);
    if (value) next.set(key, value);
  }
  const qs = next.toString();
  return qs ? `/email?${qs}` : "/email";
}

function EmailDetailPageContent() {
  const params = useParams<{ id: string }>();
  const id = typeof params.id === "string" ? params.id : "";
  const searchParams = useSearchParams();
  const [email, setEmail] = useState<Email | null>(null);
  const [error, setError] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [accounts, setAccounts] = useState<EmailAccount[]>([]);

  useEffect(() => {
    if (!id) {
      setEmail(null);
      setError(true);
      setLoaded(true);
      return;
    }
    let cancelled = false;
    void getEmail(id)
      .then((result) => {
        if (!cancelled) {
          setEmail(result);
          setError(false);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (cancelled) return;
        setEmail(null);
        setError(true);
        setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  useEffect(() => {
    let cancelled = false;
    void listEmailAccounts()
      .then((list) => {
        if (!cancelled) setAccounts(list);
      })
      .catch(() => {
        if (!cancelled) setAccounts([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const listHref = useMemo(() => buildListHref(searchParams), [searchParams]);

  if (!loaded) {
    return (
      <p
        className="p-6 text-sm text-muted-foreground"
        role="status"
      >
        Carregando…
      </p>
    );
  }

  return (
    <EmailReadView
      email={email}
      error={error}
      listHref={listHref}
      accounts={accounts}
    />
  );
}

export default function EmailDetailPage() {
  return (
    <Suspense
      fallback={
        <p
          className="p-6 text-sm text-muted-foreground"
          role="status"
        >
          Carregando…
        </p>
      }
    >
      <EmailDetailPageContent />
    </Suspense>
  );
}
