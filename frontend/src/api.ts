import type { ChatResponse, ErrorBody, Meta, RosterItem, ChatMessage, SessionState } from "./types";

export class ApiError extends Error {
  constructor(public status: number, public body: ErrorBody, public retryable: boolean) {
    super(body.message || body.detail || `Request failed (${status})`);
  }
}

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const retryable = (body as ErrorBody).retryable ?? (res.status >= 500 || res.status === 409);
    throw new ApiError(res.status, body as ErrorBody, retryable);
  }
  return body as T;
}

const opts: RequestInit = { credentials: "same-origin", headers: { "Content-Type": "application/json" } };

export const api = {
  meta: () => fetch("/api/meta", opts).then((r) => json<Meta>(r)),
  roster: () => fetch("/api/work-orders", opts).then((r) => json<{ work_orders: RosterItem[] }>(r)),
  createSession: () =>
    fetch("/api/sessions", { ...opts, method: "POST", body: "{}" }).then((r) =>
      json<{ session_id: string; messages: ChatMessage[]; state: SessionState }>(r),
    ),
  getSession: (id: string) =>
    fetch(`/api/sessions/${encodeURIComponent(id)}`, opts).then((r) =>
      json<{ session_id: string; messages: ChatMessage[]; state: SessionState }>(r),
    ),
  /** Sends a message. The same requestId must be reused for a retry of the same text. */
  async send(sessionId: string, requestId: string, message: string): Promise<ChatResponse> {
    let res: Response;
    try {
      res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/messages`, {
        ...opts,
        method: "POST",
        body: JSON.stringify({ request_id: requestId, message }),
      });
    } catch {
      // Delivery uncertain: ask the server whether this request already completed.
      const receipt = await api.receipt(sessionId, requestId).catch(() => null);
      if (receipt) return receipt;
      throw new ApiError(0, { message: "Network error. Your message may not have been sent." }, true);
    }
    if (res.status === 202) return api.waitForReceipt(sessionId, requestId);
    return json<ChatResponse>(res);
  },
  async receipt(sessionId: string, requestId: string): Promise<ChatResponse | null> {
    const res = await fetch(`/api/sessions/${encodeURIComponent(sessionId)}/requests/${requestId}`, opts);
    if (res.status === 404 || res.status === 202) return null;
    return json<ChatResponse>(res);
  },
  async waitForReceipt(sessionId: string, requestId: string): Promise<ChatResponse> {
    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      const got = await api.receipt(sessionId, requestId);
      if (got) return got;
    }
    throw new ApiError(504, { message: "Still processing. Check again in a moment." }, true);
  },
};

export function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return "10000000-1000-4000-8000-100000000000".replace(/[018]/g, (c) =>
    (+c ^ (crypto.getRandomValues(new Uint8Array(1))[0] & (15 >> (+c / 4)))).toString(16),
  );
}
