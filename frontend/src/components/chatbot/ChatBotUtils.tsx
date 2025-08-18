import { ChatMessagePayload } from "../../slices/agentic/agenticOpenApi";

// Unique key for a message in a session
export const keyOf = (m: ChatMessagePayload) => `${m.session_id}-${m.exchange_id}-${m.rank}`;

// Replace-or-insert one message, then keep array sorted by (rank asc, timestamp asc as tiebreaker)
export const upsertOne = (all: ChatMessagePayload[], m: ChatMessagePayload) => {
  const k = keyOf(m);
  const idx = all.findIndex((x) => keyOf(x) === k);
  if (idx >= 0) {
    const updated = [...all];
    updated[idx] = m; // overwrite (most recent wins)
    return sortMessages(updated);
  }
  return sortMessages([...all, m]);
};

export const sortMessages = (arr: ChatMessagePayload[]) =>
  [...arr].sort((a, b) => {
    if (a.rank !== b.rank) return a.rank - b.rank;
    // tiebreaker to stabilize UI (handles multiple thought/tool_result with same rank)
    const ta = a.timestamp || "";
    const tb = b.timestamp || "";
    return ta.localeCompare(tb);
  });

export const mergeAuthoritative = (existing: ChatMessagePayload[], finals: ChatMessagePayload[]) => {
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
