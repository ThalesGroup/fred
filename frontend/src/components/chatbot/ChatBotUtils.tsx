import { ChatMessage } from "../../slices/agentic/agenticOpenApi";

// Replace-or-insert one message, then keep array sorted by (rank asc, timestamp asc as tiebreaker)
export const upsertOne = (all: ChatMessage[], m: ChatMessage) => {
  const k = keyOf(m);
  const idx = all.findIndex((x) => keyOf(x) === k);
  if (idx >= 0) {
    const updated = [...all];
    updated[idx] = m; // overwrite (most recent wins)
    return sortMessages(updated);
  }
  return sortMessages([...all, m]);
};

export const sortMessages = (arr: ChatMessage[]) =>
  [...arr].sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank;
    // tiebreaker to stabilize UI (handles multiple thought/tool_result with same rank)
    const ta = a.timestamp || "";
    const tb = b.timestamp || "";
    return ta.localeCompare(tb);
  });

export const mergeAuthoritative = (existing: ChatMessage[], finals: ChatMessage[]) => {
  // Build maps by key
  const map = new Map(existing.map((m) => [keyOf(m), m]));
  for (const f of finals) map.set(keyOf(f), f); // overwrite existing or insert new
  return sortMessages([...map.values()]);
};

// Convert http(s) API base to ws(s) chat endpoint reliably
export const toWsUrl = (base: string | undefined, path: string) => {
  const url = new URL((base || "http://localhost") + path);
  if (url.protocol === "http:") url.protocol = "ws:";
  if (url.protocol === "https:") url.protocol = "wss:";
  return url.toString();
};


export const keyOf = (m: ChatMessage) =>
  `${m.session_id}|${m.exchange_id}|${m.rank}|${m.role}|${m.channel}`;

export const isToolCall = (m: ChatMessage) =>
  m.role === "assistant" && m.channel === "tool_call" && m.parts?.[0]?.type === "tool_call";

export const isToolResult = (m: ChatMessage) =>
  m.role === "tool" && m.channel === "tool_result" && m.parts?.[0]?.type === "tool_result";

export const hasNonEmptyText = (m: ChatMessage) =>
  (m.parts ?? []).some(p => p.type === "text" && p.text && p.text.trim().length > 0);

export const getExtras = (m: ChatMessage) => m.metadata?.extras ?? {};

export const toolId = (m: ChatMessage) =>
  (m.parts?.[0] as any)?.call_id ?? (m.parts?.[0] as any)?.id ?? "";