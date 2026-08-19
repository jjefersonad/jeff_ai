"use client";

/**
 * Chat-toolbar affordance for picking the agent profile for the current thread.
 *
 * Opens `<AssistantModal />`, which lists `GET /api/agent-profiles`. The
 * selection persists `profileId` in `localStorage["deep-agent-config"]`
 * alongside the unchanged graph id `assistantId` (typically `"unified"`).
 *
 * Keyboard: the underlying `Button` is a real `<button>`, so `Enter` /
 * `Space` open the modal without extra wiring.
 */

import { useEffect, useState } from "react";
import { Bot } from "lucide-react";

import { saveConfig } from "@/lib/config";
import { Button } from "@/components/ui/button";
import { AssistantModal } from "@/app/components/AssistantModal";
import {
  listAgentProfiles,
  type AgentProfile,
} from "@/lib/agent-profiles";

interface AssistantButtonProps {
  /**
   * LangGraph graph id (typically `"unified"`). Never overwritten with a
   * profile UUID.
   */
  assistantId: string;
  /** Currently selected agent-profile UUID, if any. */
  profileId?: string;
  /**
   * Optional callback fired after a profile is chosen. The default
   * behaviour is to persist via `saveConfig` keeping `assistantId` intact.
   * Pass a custom callback to also update React state (so the next submit
   * picks up the new id without a reload).
   */
  onChange?: (profileId: string) => void;
}

export function AssistantButton({
  assistantId,
  profileId,
  onChange,
}: AssistantButtonProps) {
  const [open, setOpen] = useState(false);
  const [selectedProfileId, setSelectedProfileId] = useState(profileId);
  const [profiles, setProfiles] = useState<AgentProfile[]>([]);

  useEffect(() => {
    setSelectedProfileId(profileId);
  }, [profileId]);

  useEffect(() => {
    listAgentProfiles().then(setProfiles);
  }, []);

  const handleSelect = (nextProfileId: string) => {
    const cleared = nextProfileId === "";
    setSelectedProfileId(cleared ? undefined : nextProfileId);
    if (onChange) {
      onChange(nextProfileId);
    } else if (cleared) {
      saveConfig({ assistantId });
    } else {
      saveConfig({ assistantId, profileId: nextProfileId });
    }
    setOpen(false);
  };

  const selectedName = profiles.find((row) => row.id === selectedProfileId)?.name;

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="sm"
        onClick={() => setOpen(true)}
        aria-label="Escolher agente"
        aria-haspopup="dialog"
        aria-expanded={open}
        title={`Agente: ${selectedName ?? "padrão"} — clique para trocar`}
      >
        <Bot aria-hidden="true" />
        <span>Agente: {selectedName ?? "padrão"}</span>
      </Button>
      <AssistantModal
        open={open}
        onOpenChange={setOpen}
        currentProfileId={selectedProfileId}
        onSelect={handleSelect}
      />
    </>
  );
}
