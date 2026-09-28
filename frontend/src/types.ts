// Mirrors backend/app/agent.py ChatService responses. Keep in sync with docs/api.md.
export type Outcome = "answered" | "acted" | "refused" | "clarification" | "error";

export interface KnowledgeSource {
  kind: "knowledge";
  section_id: string;
  heading: string;
  content_hash: string;
  text: string;
  quotes: string[];
  related: boolean;
}

export interface WorkOrderCard {
  id: string;
  title: string;
  assetType: string;
  status: string;
  dueDate: string;
  steps: string[];
  version: number;
  escalated: boolean;
  allowedNextStatus: string | null;
  notes?: { id: string; text: string; createdAt: string }[];
  notesTruncated?: boolean;
  escalations?: { id: string; reason: string; createdAt: string }[];
}

export interface ActionReceipt {
  tool: string | null;
  work_order_id?: string;
  code: string;
  ok: boolean;
  status?: string;
  previousStatus?: string;
  allowedNextStatus?: string | null;
  text?: string;
  reason?: string;
  version?: number;
  at?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  sources?: KnowledgeSource[];
  cards?: WorkOrderCard[];
  action?: ActionReceipt | null;
  missing?: string[];
  verified?: boolean;
  outcome?: Outcome;
  created_at?: string;
  pending?: boolean;
}

export interface SessionState {
  active_work_order_id: string | null;
  candidates: string[];
  needs_clarification: boolean;
}

export interface ChatResponse {
  request_id: string;
  session_id: string;
  outcome: Outcome;
  messages: ChatMessage[];
  state: SessionState;
  action: ActionReceipt | null;
  retryable: boolean;
  meta?: { model_calls: number; tool_calls: number; latency_ms: number; provider: string; is_llm: boolean };
}

export interface ErrorBody {
  outcome?: "error";
  code?: string;
  message?: string;
  detail?: string;
  retryable?: boolean;
}

export interface RosterItem {
  id: string;
  title: string;
  assetType: string;
  status: string;
  dueDate: string;
  version: number;
  escalated: boolean;
  noteCount: number;
  allowedNextStatus: string | null;
}

export interface Meta {
  technician: { id: string; name: string };
  provider: string;
  model: string;
  is_llm: boolean;
  prompt_version: string;
  kb_hash: string;
  limits: { max_message_chars: number };
}
