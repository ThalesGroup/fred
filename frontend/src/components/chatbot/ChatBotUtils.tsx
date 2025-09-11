import { ChatMessage } from "../../slices/agentic/agenticOpenApi";
import React from "react";

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
  (m.parts ?? []).some((p) => p.type === "text" && p.text && p.text.trim().length > 0);

export const getExtras = (m: ChatMessage) => m.metadata?.extras ?? {};

export const toolId = (m: ChatMessage) =>
  (m.parts?.[0] as any)?.call_id ?? (m.parts?.[0] as any)?.id ?? "";

// ---- Parts typing ----
type Part =
  | ({ type: "text"; text: string } & Record<string, unknown>)
  | ({ type: "code"; code: string; language?: string } & Record<string, unknown>)
  | ({ type: "image_url"; url: string; alt?: string } & Record<string, unknown>)
  | ({ type: "tool_call"; name: string; args?: unknown } & Record<string, unknown>)
  | ({ type: "tool_result"; ok?: boolean; content?: string } & Record<string, unknown>);

const isTextPart = (p: Part): p is Extract<Part, { type: "text" }> => p.type === "text";
const isToolCallPart = (p: Part): p is Extract<Part, { type: "tool_call" }> => p.type === "tool_call";
const isToolResultPart = (p: Part): p is Extract<Part, { type: "tool_result" }> =>
  p.type === "tool_result";

/** Safe truncate helper */
const ellipsize = (s: string, max: number) => (s.length > max ? `${s.slice(0, max)}…` : s);

// ---- Minimal status dot + text ----
function StatusBadge({
  ok,
  text,
  title,
}: {
  ok: boolean | undefined | null;
  text: string;
  title?: string;
}) {
  const dotClass =
    ok === true ? "bg-green-500" : ok === false ? "bg-red-500" : "bg-gray-400";

  const aria =
    ok === true ? "Succeeded" : ok === false ? "Failed" : "Unknown status";

  return (
    <span
      className="inline-flex items-center gap-2 text-sm text-muted-foreground"
      aria-label={`Tool result: ${aria}`}
      title={title ?? aria}
    >
      <span className={`h-2 w-2 rounded-full ${dotClass}`} />
      <span className="truncate max-w-[32ch]">{text}</span>
    </span>
  );
}

// Returns a ReactNode so you can render either plain text or JSX badges.
export function textPreview(m: ChatMessage): React.ReactNode {
  const parts = (m.parts ?? []) as Part[];

  // Prefer concatenated text parts
  const txt = parts
    .filter(isTextPart)
    .map((p) => (p.text ?? "").trim())
    .filter(Boolean)
    .join(" ");

  if (txt) return ellipsize(txt, 40);

  // Tool call / result quick previews
  const p0 = parts[0];

  if (p0 && isToolCallPart(p0)) {
    const name = p0.name || "tool";
    const argsStr = p0.args !== undefined ? JSON.stringify(p0.args) : "";
    return `${name}(${ellipsize(argsStr, 40)})`;
  }

  if (p0 && isToolResultPart(p0)) {
    const ok = p0.ok ?? null;
    const content = ellipsize(p0.content ?? "", 40);
    return <StatusBadge ok={ok} text={content} />;
  }

  // Fallbacks by channel
  switch (m.channel) {
    case "plan":
      return "Plan";
    case "thought":
      return "Thought";
    case "observation":
      return "Observation";
    case "tool_call":
      return "Tool call";
    case "tool_result":
      return "Tool result";
    case "system_note":
      return "System note";
    case "error":
      return "Error";
    default:
      return m.channel;
  }
}
