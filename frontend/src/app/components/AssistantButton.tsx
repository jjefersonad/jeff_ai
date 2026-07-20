"use client";

/**
 * Chat-toolbar affordance for picking the assistant for the current thread.
 *
 * Renders a `Button` with the label "Assistant: <id>" that opens the
 * `<AssistantModal />`. The selection is **advisory** today: per
 * `frontend-menu-redesign` / `chat-assistant-selector` REQ-003, the choice is
 * persisted to `localStorage["deep-agent-config"]` via `saveConfig`, but the
 * backend graph wiring still goes through `unified` regardless (the mode
 * system is a known facade — see CLAUDE.md Known Debt #1).
 *
 * Keyboard: the underlying `Button` is a real `<button>`, so `Enter` /
 * `Space` open the modal without extra wiring.
 */

import { useState } from "react";
import { Bot } from "lucide-react";

import { saveConfig } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { AssistantModal } from "@/app/components/AssistantModal";

interface AssistantButtonProps {
  /**
   * Currently selected assistant id. Defaults to `"unified"` if no config is
   * saved. The button label is derived from this value.
   */
  assistantId: string;
  /**
   * Optional callback fired after a new assistant is chosen. The default
   * behaviour is to persist via `saveConfig`. Pass a custom callback to take
   * ownership of persistence (e.g. when the parent already maintains a copy
   * of the config in React state).
   */
  onChange?: (assistantId: string) => void;
}

export function AssistantButton({ assistantId, onChange }: AssistantButtonProps) {
  const [open, setOpen] = useState(false);

  const handleSelect = (nextId: string) => {
    if (onChange) {
      onChange(nextId);
    } else {
      saveConfig({ assistantId: nextId });
    }
    setOpen(false);
  };

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setOpen(true)}
        aria-label="Choose assistant"
        aria-haspopup="dialog"
        aria-expanded={open}
        title={`Assistant: ${assistantId} — click to change`}
      >
        <Bot aria-hidden="true" />
        <span>Assistant: {assistantId}</span>
      </Button>
      <AssistantModal
        open={open}
        onOpenChange={setOpen}
        currentAssistantId={assistantId}
        onSelect={handleSelect}
      />
    </>
  );
}
