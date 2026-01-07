// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import type {
  ChatMessage,
  CodePart,
  ImageUrlPart,
  TextPart,
  ToolCallPart,
  ToolResultPart,
} from "../../slices/agentic/agenticOpenApi";

export type MessagePart = ChatMessage["parts"][number];

// --- guards ---
export const isTextPart = (p: MessagePart): p is Extract<MessagePart, { type: "text" }> => p.type === "text";
export const isCodePart = (p: MessagePart): p is Extract<MessagePart, { type: "code" }> => p.type === "code";
export const isImageUrlPart = (p: MessagePart): p is Extract<MessagePart, { type: "image_url" }> =>
  p.type === "image_url";
export const isToolCallPart = (p: MessagePart): p is Extract<MessagePart, { type: "tool_call" }> =>
  p.type === "tool_call";
export const isToolResultPart = (p: MessagePart): p is Extract<MessagePart, { type: "tool_result" }> =>
  p.type === "tool_result";

// --- internal helpers ---
const TOOL_ARGS_PREVIEW_MAX = 200;
const TOOL_RESULT_PREVIEW_MAX = 400;

const tryStringify = (v: unknown): string => {
  try {
    return JSON.stringify(v);
  } catch {
    return String(v ?? "");
  }
};

const ellipsize = (s: string, max: number) => (s.length > max ? s.slice(0, max) + "…" : s);

const tryPrettyJSON = (s: string): string => {
  try {
    const obj = JSON.parse(s);
    return JSON.stringify(obj, null, 2);
  } catch {
    return s;
  }
};

// --- text/code aggregation ---
export function toMarkdown(parts?: MessagePart[] | null, includeCode = true): string {
  if (!parts?.length) return "";
  const out: string[] = [];
  for (const p of parts) {
    if (isTextPart(p)) out.push(p.text ?? "");
    else if (includeCode && isCodePart(p)) {
      const lang = p.language ?? "";
      out.push("```" + lang, p.code ?? "", "```");
    }
  }
  return out.join("\n\n").trim();
}

export function toPlainText(parts?: MessagePart[] | null): string {
  if (!parts?.length) return "";
  return parts
    .filter(isTextPart)
    .map((p) => p.text ?? "")
    .join("\n\n")
    .trim();
}

export const toSpeechText = toPlainText;
export const toCopyText = (parts?: MessagePart[] | null) => toMarkdown(parts, true);

// --- UI-display chunks for non-text parts ---
export type DisplayChunk =
  | { kind: "text"; text: string }
  | { kind: "code"; code: string; language?: string | null }
  | { kind: "image"; url: string; alt?: string | null }
  | { kind: "tool_call"; callId: string; name: string; argsPreview: string }
  | { kind: "tool_result"; callId: string; ok?: boolean | null; latencyMs?: number | null; contentPreview: string };

export function toDisplayChunks(parts?: MessagePart[] | null): DisplayChunk[] {
  if (!parts?.length) return [];
  const chunks: DisplayChunk[] = [];
  for (const p of parts) {
    if (isTextPart(p)) {
      const t = (p.text ?? "").toString();
      if (t.trim()) chunks.push({ kind: "text", text: t });
    } else if (isCodePart(p)) {
      chunks.push({ kind: "code", code: p.code ?? "", language: p.language ?? null });
    } else if (isImageUrlPart(p)) {
      chunks.push({ kind: "image", url: p.url, alt: p.alt ?? null });
    } else if (isToolCallPart(p)) {
      const argsPreview = ellipsize(tryStringify(p.args), TOOL_ARGS_PREVIEW_MAX);
      chunks.push({ kind: "tool_call", callId: p.call_id, name: p.name, argsPreview });
    } else if (isToolResultPart(p)) {
      const pretty = tryPrettyJSON(p.content ?? "");
      const contentPreview = ellipsize(pretty, TOOL_RESULT_PREVIEW_MAX);
      chunks.push({ kind: "tool_result", callId: p.call_id, ok: p.ok, latencyMs: p.latency_ms, contentPreview });
    }
  }
  return chunks;
}

// --- partitions if you want tabs/columns ---
export function partition(parts?: MessagePart[] | null) {
  const text: TextPart[] = [];
  const code: CodePart[] = [];
  const images: ImageUrlPart[] = [];
  const calls: ToolCallPart[] = [];
  const results: ToolResultPart[] = [];
  for (const p of parts ?? []) {
    if (isTextPart(p)) text.push(p);
    else if (isCodePart(p)) code.push(p);
    else if (isImageUrlPart(p)) images.push(p);
    else if (isToolCallPart(p)) calls.push(p);
    else if (isToolResultPart(p)) results.push(p);
  }
  return { text, code, images, calls, results };
}
