/**
 * Per-thread frontend configuration persisted in `localStorage` under
 * `CONFIG_KEY`. Holds the assistant id used by the toolbar `AssistantButton`
 * and the chat composer.
 *
 * Historically this also held the LangSmith API key (`langsmithApiKey`).
 * Per `frontend-menu-redesign` / `langsmith-api-key-config` REQ-001, the key
 * is no longer stored, read, or transmitted by the frontend — the backend
 * reads `LANGSMITH_API_KEY` from the environment instead. To preserve data
 * hygiene for users who still have a legacy payload in `localStorage`, the
 * `langsmithApiKey` field is silently stripped on read and never re-emitted
 * on write.
 */
export interface StandaloneConfig {
  assistantId: string;
}

// Graph entrypoint used when no config has been saved yet. `unified` is the
// real graph — `agent`/`sdd_agent`/`assistant` are back-compat shims that run
// the same code (see CLAUDE.md).
export const DEFAULT_ASSISTANT_ID = "unified";

const CONFIG_KEY = "deep-agent-config";

export function getConfig(): StandaloneConfig | null {
  if (typeof window === "undefined") return null;

  const stored = localStorage.getItem(CONFIG_KEY);
  if (!stored) return null;

  try {
    const parsed = JSON.parse(stored) as Partial<StandaloneConfig> & {
      // Legacy field, no longer in `StandaloneConfig`. Declared here so the
      // strip below type-checks without `any` and so future readers know the
      // shape we explicitly ignore.
      langsmithApiKey?: unknown;
    };
    if (typeof parsed.assistantId !== "string" || parsed.assistantId === "") {
      return null;
    }
    return { assistantId: parsed.assistantId };
  } catch {
    return null;
  }
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
