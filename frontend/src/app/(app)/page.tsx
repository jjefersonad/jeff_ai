"use client";

import React, { useState, useEffect, useCallback, Suspense } from "react";
import { useQueryState } from "nuqs";
import {
  getConfig,
  saveConfig,
  StandaloneConfig,
  DEFAULT_ASSISTANT_ID,
} from "@/lib/config";
import { Button } from "@/components/ui/button";
import { Assistant } from "@langchain/langgraph-sdk";
import { ClientProvider, useClient } from "@/providers/ClientProvider";
import { MessagesSquare, SquarePen } from "lucide-react";
import {
  ResizableHandle,
  ResizablePanel,
  ResizablePanelGroup,
} from "@/components/ui/resizable";
import { ThreadList } from "@/app/components/ThreadList";
import { ChatProvider } from "@/providers/ChatProvider";
import { ChatInterface } from "@/app/components/ChatInterface";

interface HomePageInnerProps {
  config: StandaloneConfig;
}

/**
 * Chat route content. The authenticated shell (top bar, sidebar,
 * `NavSidebarProvider`) is provided by the parent `(app)/layout.tsx`.
 * This file is responsible only for the chat panel itself plus the
 * chat-specific controls (`Conversas` thread-history toggle and
 * `New Thread`).
 */
function ChatPageInner({ config }: HomePageInnerProps) {
  const client = useClient();
  const [threadId, setThreadId] = useQueryState("threadId");
  const [sidebar, setSidebar] = useQueryState("sidebar");

  const [mutateThreads, setMutateThreads] = useState<(() => void) | null>(null);
  const [interruptCount, setInterruptCount] = useState(0);
  const [assistant, setAssistant] = useState<Assistant | null>(null);

  const fetchAssistant = useCallback(async () => {
    const isUUID =
      /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(
        config.assistantId
      );

    if (isUUID) {
      // We should try to fetch the assistant directly with this UUID
      try {
        const data = await client.assistants.get(config.assistantId);
        setAssistant(data);
      } catch (error) {
        console.error("Failed to fetch assistant:", error);
        setAssistant({
          assistant_id: config.assistantId,
          graph_id: config.assistantId,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          config: {},
          metadata: {},
          version: 1,
          name: "Assistant",
          context: {},
        });
      }
    } else {
      try {
        // We should try to list out the assistants for this graph, and then use the default one.
        // TODO: Paginate this search, but 100 should be enough for graph name
        const assistants = await client.assistants.search({
          graphId: config.assistantId,
          limit: 100,
        });
        const defaultAssistant = assistants.find(
          (assistant) => assistant.metadata?.["created_by"] === "system"
        );
        if (defaultAssistant === undefined) {
          throw new Error("No default assistant found");
        }
        setAssistant(defaultAssistant);
      } catch (error) {
        console.error(
          "Failed to find default assistant from graph_id: try setting the assistant_id directly:",
          error
        );
        setAssistant({
          assistant_id: config.assistantId,
          graph_id: config.assistantId,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          config: {},
          metadata: {},
          version: 1,
          name: config.assistantId,
          context: {},
        });
      }
    }
  }, [client, config.assistantId]);

  useEffect(() => {
    fetchAssistant();
  }, [fetchAssistant]);

  return (
    <div className="flex h-full flex-col">
      {/* Chat-specific toolbar: thread-history toggle + new-thread action.
          The authenticated shell (top bar + sidebar) lives in the parent
          (app)/layout.tsx; this bar is page-specific and lives in the slot. */}
      <div className="flex items-center gap-2 border-b border-border bg-card px-4 py-2">
        {!sidebar && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setSidebar("1")}
            className="rounded-md border border-border bg-card text-foreground hover:bg-accent"
          >
            <MessagesSquare className="mr-2 h-4 w-4" />
            Conversas
            {interruptCount > 0 && (
              <span className="ml-2 inline-flex min-h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] text-destructive-foreground">
                {interruptCount}
              </span>
            )}
          </Button>
        )}
        <Button
          variant="outline"
          size="sm"
          onClick={() => setThreadId(null)}
          disabled={!threadId}
          className="ml-auto border-[#2F6868] bg-[#2F6868] text-white hover:bg-[#2F6868]/80"
        >
          <SquarePen className="mr-2 h-4 w-4" />
          New Thread
        </Button>
      </div>
      <div className="flex-1 overflow-hidden">
        <ResizablePanelGroup
          direction="horizontal"
          autoSaveId="standalone-chat"
        >
          {sidebar && (
            <>
              <ResizablePanel
                id="thread-history"
                order={1}
                defaultSize={25}
                minSize={20}
                className="relative min-w-[380px]"
              >
                <ThreadList
                  onThreadSelect={async (id) => {
                    await setThreadId(id);
                  }}
                  onMutateReady={(fn) => setMutateThreads(() => fn)}
                  onClose={() => setSidebar(null)}
                  onInterruptCountChange={setInterruptCount}
                />
              </ResizablePanel>
              <ResizableHandle />
            </>
          )}

          <ResizablePanel
            id="chat"
            className="relative flex flex-col"
            order={2}
          >
            <ChatProvider
              activeAssistant={assistant}
              onHistoryRevalidate={() => mutateThreads?.()}
            >
              <ChatInterface
                assistant={assistant}
                assistantId={config.assistantId}
              />
            </ChatProvider>
          </ResizablePanel>
        </ResizablePanelGroup>
      </div>
    </div>
  );
}

function ChatPageContent() {
  const [config, setConfig] = useState<StandaloneConfig | null>(null);
  const [assistantId, setAssistantId] = useQueryState("assistantId");

  // On mount, check for saved config; otherwise auto-provision a default.
  // The backend URL is fixed via NEXT_PUBLIC_API_URL (see lib/api.ts) — Jeff
  // AI is self-hosted with exactly one deployment, so there's no first-run
  // Settings step. The persisted config now only tracks the assistant graph
  // id; the LangSmith API key (formerly here) is read from the backend env
  // var `LANGSMITH_API_KEY` (see `langsmith-api-key-config`).
  useEffect(() => {
    const savedConfig = getConfig();
    if (savedConfig) {
      setConfig(savedConfig);
      if (!assistantId) {
        setAssistantId(savedConfig.assistantId);
      }
    } else {
      const defaultConfig: StandaloneConfig = {
        assistantId: DEFAULT_ASSISTANT_ID,
      };
      saveConfig(defaultConfig);
      setConfig(defaultConfig);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // If config changes, update the assistantId
  useEffect(() => {
    if (config && !assistantId) {
      setAssistantId(config.assistantId);
    }
  }, [config, assistantId, setAssistantId]);

  if (!config) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-muted-foreground">Loading...</p>
      </div>
    );
  }

  return <ChatPageInner config={config} />;
}

export default function ChatPage() {
  return (
    <ClientProvider>
      <Suspense
        fallback={
          <div className="flex h-full items-center justify-center">
            <p className="text-muted-foreground">Loading...</p>
          </div>
        }
      >
        <ChatPageContent />
      </Suspense>
    </ClientProvider>
  );
}
