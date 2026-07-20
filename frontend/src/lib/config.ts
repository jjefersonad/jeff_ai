export interface StandaloneConfig {
  assistantId: string;
  langsmithApiKey?: string;
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
    return JSON.parse(stored);
  } catch {
    return null;
  }
}

export function saveConfig(config: StandaloneConfig): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(CONFIG_KEY, JSON.stringify(config));
}
