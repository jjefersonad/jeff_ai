/**
 * Per-thread frontend configuration persisted in `localStorage` under
 * `CONFIG_KEY`. Holds the LangGraph graph id (`assistantId`, typically
 * `"unified"`) and an optional `profileId` (UUID of an `AgentProfile`).
 * The two MUST stay distinct: `assistantId` is never overwritten with the
 * profile UUID.
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
  /** UUID of the selected `AgentProfile`. Distinct from `assistantId` (graph id). */
  profileId?: string;
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
    const profileId =
      typeof parsed.profileId === "string" && parsed.profileId !== ""
        ? parsed.profileId
        : undefined;
    return {
      assistantId: parsed.assistantId,
      ...(profileId ? { profileId } : {}),
    };
  } catch {
    return null;
  }
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  const stored: StandaloneConfig = {
    assistantId: config.assistantId,
    ...(config.profileId ? { profileId: config.profileId } : {}),
  };
  localStorage.setItem(CONFIG_KEY, JSON.stringify(stored));
}
