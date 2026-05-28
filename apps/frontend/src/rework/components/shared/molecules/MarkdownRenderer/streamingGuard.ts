// Copyright Thales 2026
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

export type StreamingFenceKind = "code" | "math" | "directive";

export interface PendingStreamingFence {
  kind: StreamingFenceKind;
  content: string;
  label?: string;
}

export interface StreamingMarkdownState {
  stableMarkdown: string;
  pendingFence: PendingStreamingFence | null;
}

interface OpenFenceState {
  kind: StreamingFenceKind;
  fenceChar: "`" | "$" | ":";
  fenceMinLen: number;
  openerLine: number;
  label?: string;
}

/**
 * Splits a streaming markdown string into:
 * - `stableMarkdown`: content safe to hand to ReactMarkdown immediately
 * - `pendingFence`: the last still-open fence, if any
 *
 * Why it exists:
 * Streaming markdown often arrives in the middle of a fenced block. Mermaid,
 * KaTeX, and syntax highlighting all expect complete syntax units.
 *
 * How to use:
 * - render `stableMarkdown` through the normal markdown pipeline
 * - optionally render `pendingFence` with a specialized streaming preview
 * - once the closing delimiter arrives, `pendingFence` becomes null and the
 *   complete block flows back through markdown as usual
 *
 * CommonMark §4.5 rules applied:
 *  1. Openers are only recognised at line start (≤3 leading spaces).
 *  2. Once inside a fence, inner fence-like text is ignored — only the
 *     matching closer is sought.
 *  3. The closing fence must use the same character and length as the opener.
 */
export function getStreamingMarkdownState(text: string): StreamingMarkdownState {
  const lines = text.split("\n");

  let openFence: OpenFenceState | null = null;

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const trimmed = raw.trimStart();
    const indent = raw.length - trimmed.length;

    if (openFence === null) {
      if (indent > 3) continue;

      const btMatch = /^(`{3,})(.*)$/.exec(trimmed);
      if (btMatch) {
        const label = btMatch[2].trim().split(/\s+/, 1)[0] || undefined;
        openFence = {
          kind: "code",
          fenceChar: "`",
          fenceMinLen: btMatch[1].length,
          openerLine: i,
          label,
        };
        continue;
      }
      if (trimmed === "$$") {
        openFence = {
          kind: "math",
          fenceChar: "$",
          fenceMinLen: 2,
          openerLine: i,
        };
        continue;
      }
      const directiveMatch = /^:::([a-zA-Z][\w-]*)/.exec(trimmed);
      if (directiveMatch) {
        openFence = {
          kind: "directive",
          fenceChar: ":",
          fenceMinLen: 3,
          openerLine: i,
          label: directiveMatch[1],
        };
        continue;
      }
    } else {
      const stripped = trimmed.trimEnd();
      if (openFence.fenceChar === "`" && indent <= 3) {
        const closeMatch = /^(`{3,})$/.exec(stripped);
        if (closeMatch && closeMatch[1].length >= openFence.fenceMinLen) openFence = null;
      } else if (openFence.fenceChar === "$" && stripped === "$$") {
        openFence = null;
      } else if (openFence.fenceChar === ":" && stripped === ":::") {
        openFence = null;
      }
    }
  }

  if (openFence === null) {
    return { stableMarkdown: text, pendingFence: null };
  }

  const cutAt = lines.slice(0, openFence.openerLine).reduce((acc, line) => acc + line.length + 1, 0);
  const content = lines.slice(openFence.openerLine + 1).join("\n");

  return {
    stableMarkdown: text.slice(0, cutAt),
    pendingFence: {
      kind: openFence.kind,
      content,
      label: openFence.label,
    },
  };
}

/**
 * Backward-compatible helper for callers that only need the safe markdown
 * prefix and want to hide any still-open fenced block.
 */
export function streamingGuard(text: string): string {
  return getStreamingMarkdownState(text).stableMarkdown;
}
