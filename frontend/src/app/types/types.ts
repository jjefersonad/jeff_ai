export interface ToolCall {
  id: string;
  name: string;
  args: Record<string, unknown>;
  result?: string;
  status: "pending" | "completed" | "error" | "interrupted";
}

export interface SubAgent {
  id: string;
  name: string;
  subAgentName: string;
  input: Record<string, unknown>;
  output?: Record<string, unknown>;
  status: "pending" | "active" | "completed" | "error";
}

export interface FileItem {
  path: string;
  content: string;
}

export interface TodoItem {
  id: string;
  content: string;
  status: "pending" | "in_progress" | "completed";
  updatedAt?: Date;
}

export interface Thread {
  id: string;
  title: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface InterruptData {
  value: any;
  ns?: string[];
  scope?: string;
}

export interface ActionRequest {
  name: string;
  args: Record<string, unknown>;
  description?: string;
}

export interface ReviewConfig {
  actionName: string;
  allowedDecisions?: string[];
}

export interface ToolApprovalInterruptData {
  action_requests: ActionRequest[];
  review_configs?: ReviewConfig[];
}

// ---------------------------------------------------------------------------
// Envelope proposal interrupt (mirrors backend
// `src/agents/unified/envelope_proposal.py:propose_envelope_tool`). This is
// a DIFFERENT interrupt shape from `ToolApprovalInterruptData` above — it
// comes from a raw `interrupt()` call, not the `HumanInTheLoopMiddleware`'s
// `action_requests`/`decisions` protocol, so it resumes with a
// `EnvelopeGrantDecision`, not a `{decisions: [...]}` payload.
// ---------------------------------------------------------------------------
export interface EnvelopeCapabilityProposal {
  capability: string;
  justification: string;
}

export interface EnvelopeProposal {
  required_capabilities: EnvelopeCapabilityProposal[];
  excluded_capabilities: string[];
}

export interface EnvelopeProposalInterruptData {
  type: "envelope_proposal";
  proposal: EnvelopeProposal;
  contradiction_warning?: string;
}

export interface EnvelopeGrantDecision {
  granted_capabilities: string[];
  edited: boolean;
  rejected: boolean;
}
