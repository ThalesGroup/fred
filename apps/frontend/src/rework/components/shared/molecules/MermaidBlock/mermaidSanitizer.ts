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

const NODE_LABEL_REGEX = /(\b[A-Za-z_][A-Za-z0-9_]*)\[([^\]\n]+)\]/g;

const FLOWCHART_HEADER_REGEX = /^\s*(?:%%[^\n]*\n|\s*\n)*\s*(?:flowchart|graph)\b/;

// Complete edge tokens only (-->, ---, -.->, ==>, <-->, plus an optional
// |label|). The two-dash opener of "A -- text --> B" must not match, or the
// edge text would be mistaken for a node endpoint.
const EDGE_DELIMITER_REGEX = /(\s*(?:<-{2,}>|-{2,}>|-{3,}|-\.+->|<?={2,}>|={3,})\s*(?:\|[^|]*\|\s*)?)/;

const BARE_MULTI_WORD_NODE_REGEX = /^[\p{L}_][\p{L}\p{N}_]*(?:[ \t]+[\p{L}\p{N}_]+)+$/u;

function toSafeNodeId(label: string): string {
  return label
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^A-Za-z0-9_]+/g, "_");
}

/**
 * Rewrites a bare multi-word token used as an edge endpoint - a node label
 * referenced directly instead of through its declared ID, e.g.
 * `OpenSearch --> LLM Azure` - into a generated safe ID with the original
 * text as a quoted label: `OpenSearch --> LLM_Azure["LLM Azure"]`.
 *
 * The ID derivation is deterministic, so every reference to the same label
 * converges on the same node. Flowcharts only: other diagram types (sequence,
 * state) legitimately place free text next to arrows.
 */
function repairBareMultiWordNodeRefs(code: string): string {
  if (!FLOWCHART_HEADER_REGEX.test(code)) return code;

  return code
    .split("\n")
    .map((line) => {
      if (line.trimStart().startsWith("%%")) return line;

      const parts = line.split(EDGE_DELIMITER_REGEX);
      if (parts.length < 3) return line;

      return parts
        .map((part, index) => {
          const isEdgeToken = index % 2 === 1;
          if (isEdgeToken) return part;

          const endpoint = part.trim();
          if (!BARE_MULTI_WORD_NODE_REGEX.test(endpoint)) return part;

          return part.replace(endpoint, `${toSafeNodeId(endpoint)}["${endpoint}"]`);
        })
        .join("");
    })
    .join("\n");
}

/**
 * Best-effort Mermaid sanitizer for common LLM formatting issues.
 *
 * Why it exists:
 * Mermaid parsing is strict for node labels and line-break syntax. LLM outputs
 * often contain literal backslash-n sequences, unquoted labels that include
 * parser-sensitive text like parentheses, and bare label text used where a
 * node ID is expected.
 *
 * How to use:
 * Call this only as a fallback when raw Mermaid render fails.
 *
 * Example:
 * sanitizeMermaidForParsing('A[Web App\\n(Europe)] --> B')
 *   => 'A["Web App<br/>(Europe)"] --> B'
 */
export function sanitizeMermaidForParsing(code: string): string {
  const withBreakTags = code.replace(/\\n/g, "<br/>").replace(/<br\s*>/gi, "<br/>");

  const withQuotedLabels = withBreakTags.replace(NODE_LABEL_REGEX, (_full, nodeId: string, innerLabel: string) => {
    const label = innerLabel.trim();
    if (!label) return _full;

    const isAlreadyQuoted =
      (label.startsWith('"') && label.endsWith('"')) || (label.startsWith("'") && label.endsWith("'"));

    if (isAlreadyQuoted) return _full;

    const needsQuotes = /<br\s*\/?>/i.test(label) || /[()]/.test(label);
    if (!needsQuotes) return _full;

    return `${nodeId}["${label.replace(/"/g, "&quot;")}"]`;
  });

  return repairBareMultiWordNodeRefs(withQuotedLabels);
}
