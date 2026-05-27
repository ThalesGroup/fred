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

/**
 * Strips the last unclosed fenced block from a streaming markdown string so
 * that block renderers (Mermaid, KaTeX, syntax highlighter) never receive
 * incomplete syntax. Returns text unchanged when all fences are closed.
 *
 * CommonMark §4.5 rules applied:
 *  1. Openers are only recognised at line start (≤3 leading spaces).
 *  2. Once inside a fence, inner fence-like text is ignored — only the
 *     matching closer is sought. This prevents content inside a code block
 *     from being misidentified as a nested opener.
 *  3. The closing fence must use the same character and length as the opener.
 */
export function streamingGuard(text: string): string {
  const lines = text.split("\n");

  let fenceChar: string | null = null;
  let fenceMinLen = 0;
  let fenceOpenerLine = 0;

  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i];
    const trimmed = raw.trimStart();
    const indent = raw.length - trimmed.length;

    if (fenceChar === null) {
      if (indent > 3) continue;

      const btMatch = /^(`{3,})/.exec(trimmed);
      if (btMatch) {
        fenceChar = "`";
        fenceMinLen = btMatch[1].length;
        fenceOpenerLine = i;
        continue;
      }
      if (trimmed === "$$") {
        fenceChar = "$";
        fenceMinLen = 2;
        fenceOpenerLine = i;
        continue;
      }
      if (/^:::[a-zA-Z]/.test(trimmed)) {
        fenceChar = ":";
        fenceMinLen = 3;
        fenceOpenerLine = i;
        continue;
      }
    } else {
      const stripped = trimmed.trimEnd();
      if (fenceChar === "`" && indent <= 3) {
        const closeMatch = /^(`{3,})$/.exec(stripped);
        if (closeMatch && closeMatch[1].length >= fenceMinLen) fenceChar = null;
      } else if (fenceChar === "$" && stripped === "$$") {
        fenceChar = null;
      } else if (fenceChar === ":" && stripped === ":::") {
        fenceChar = null;
      }
    }
  }

  if (fenceChar === null) return text;

  const cutAt = lines.slice(0, fenceOpenerLine).reduce((acc, l) => acc + l.length + 1, 0);
  return text.slice(0, cutAt);
}
