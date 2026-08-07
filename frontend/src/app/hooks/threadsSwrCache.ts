import { mutate as globalMutate } from "swr";
import type { MutatorCallback, MutatorOptions } from "swr";
import type { Thread } from "@langchain/langgraph-sdk";

export type ThreadsSwrKey = {
  kind: "threads";
  /** `users.id` da sessão, ou `"anon"` quando não autenticado. */
  userId: string;
  pageIndex: number;
  pageSize: number;
  assistantId: string;
  status?: Thread["status"];
};

/** Constrói a key SWR de threads — inclui userId para isolar cache entre sessões. */
export function threadsSwrKeyFor(
  userId: string | null | undefined,
  pageIndex: number,
  pageSize: number,
  assistantId: string,
  status?: Thread["status"]
): ThreadsSwrKey {
  return {
    kind: "threads",
    userId: userId ?? "anon",
    pageIndex,
    pageSize,
    assistantId,
    status,
  };
}

export function isThreadsSwrKey(key: unknown): key is ThreadsSwrKey {
  return (
    typeof key === "object" &&
    key !== null &&
    (key as { kind?: unknown }).kind === "threads"
  );
}

type GlobalMutate = (
  filter: (key: unknown) => boolean,
  data?: unknown | Promise<unknown> | MutatorCallback,
  opts?: boolean | MutatorOptions
) => Promise<unknown>;

/** Invalida todas as páginas de threads no cache SWR (login/logout). */
export async function clearThreadsSwrCache(
  mutate: GlobalMutate = globalMutate as GlobalMutate
): Promise<void> {
  await mutate(isThreadsSwrKey, undefined, { revalidate: false });
}
