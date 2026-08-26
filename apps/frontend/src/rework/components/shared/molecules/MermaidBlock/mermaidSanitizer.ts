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

import { stripDiacritics } from "@rework/utils/stripDiacritics";

const NODE_LABEL_REGEX = /(\b[A-Za-z_][A-Za-z0-9_]*)\[([^\]\n]+)\]/g;

// Mermaid YAML frontmatter block ("---\ntitle: ...\n---"). Each iteration
// consumes exactly one full line, keeping the scan linear.
const FRONTMATTER_REGEX = /^---\r?\n(?:[^\n]*\n)*?---[ \t]*(?:\r?\n|$)/;

// Linear by construction: each loop iteration must consume a literal "%%"
// comment line, so a run of blank lines cannot be partitioned two ways (a
// nested `\s*\n` alternative here backtracks exponentially on the failure
// path - the only path that ever reaches this sanitizer).
const FLOWCHART_HEADER_REGEX = /^\s*(?:%%[^\n]*\n\s*)*(?:flowchart|graph)\b/;

// Flowchart statement keywords: text on these lines is never an edge endpoint.
const KEYWORD_LINE_REGEX = /^\s*(?:subgraph|end|direction|style|classDef|class|click|linkStyle|accTitle|accDescr)\b/;

// One complete link token, mirroring the flowchart lexer's LINK rules:
// dash/thick/dotted families with an optional x/o/< head and x/o/> (or an
// extra dash/equals) tail, the invisible link ~~~, and the & endpoint
// separator - each followed by an optional |label|. The two-dash opener of
// "A -- text --> B" does not match (the dash family needs a third symbol),
// so open edge text is never split. A trailing x/o must be followed by
// whitespace or end of line so "A --outside" is not read as a circle edge.
const EDGE_TOKEN_REGEX =
  /(?:[xo<]?(?:-{2,}(?:[xo](?=\s|$)|[->])|={2,}(?:[xo](?=\s|$)|[=>])|-\.+-(?:[xo](?=\s|$)|>)?)|~{3,}|&(?=\s))(?:\s*\|[^|]*\|)?/y;

const TOKEN_START_CHARS = new Set(["-", "=", "~", "x", "o", "<", "&"]);

const BARE_MULTI_WORD_NODE_REGEX = /^[\p{L}_][\p{L}\p{M}\p{N}_]*(?:[ \t]+[\p{L}\p{M}\p{N}_]+)+$/u;

function quoteNodeLabel(nodeId: string, label: string): string {
  return `${nodeId}["${label.replace(/"/g, "&quot;")}"]`;
}

interface DeclaredNodes {
  labelToId: Map<string, string>;
  idToLabel: Map<string, string>;
}

function normalizeLabel(raw: string): string {
  let label = raw.trim();
  const isQuoted = (label.startsWith('"') && label.endsWith('"')) || (label.startsWith("'") && label.endsWith("'"));
  if (isQuoted) label = label.slice(1, -1).trim();
  return label.normalize("NFC").replace(/\s+/g, " ");
}

function collectDeclaredNodes(code: string): DeclaredNodes {
  const labelToId = new Map<string, string>();
  const idToLabel = new Map<string, string>();
  for (const match of code.matchAll(NODE_LABEL_REGEX)) {
    const [, nodeId, rawLabel] = match;
    const label = normalizeLabel(rawLabel);
    if (!label) continue;
    if (!idToLabel.has(nodeId)) idToLabel.set(nodeId, label);
    if (!labelToId.has(label)) labelToId.set(label, nodeId);
  }
  return { labelToId, idToLabel };
}

/**
 * Splits a line into [endpoint, edgeToken, endpoint, ...] alternating parts,
 * ignoring edge-token lookalikes inside brackets or quotes (a label such as
 * `A[raw --> clean]` must not be split). Returns null when the line contains
 * no edge token.
 */
function splitOnEdgeTokens(line: string): string[] | null {
  const parts: string[] = [];
  let segmentStart = 0;
  let bracketDepth = 0;
  let quote: string | null = null;
  let i = 0;

  while (i < line.length) {
    const char = line[i];
    if (quote !== null) {
      if (char === quote) quote = null;
      i += 1;
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      i += 1;
      continue;
    }
    if (char === "[" || char === "(" || char === "{") {
      bracketDepth += 1;
      i += 1;
      continue;
    }
    if (char === "]" || char === ")" || char === "}") {
      bracketDepth = Math.max(0, bracketDepth - 1);
      i += 1;
      continue;
    }

    if (bracketDepth === 0 && TOKEN_START_CHARS.has(char)) {
      // x/o/< heads and & only count after whitespace, so the final letter
      // of an identifier like "Box" is never pulled into an edge token.
      const needsBoundary = char === "x" || char === "o" || char === "<" || char === "&";
      if (!needsBoundary || i === 0 || /\s/.test(line[i - 1])) {
        EDGE_TOKEN_REGEX.lastIndex = i;
        const match = EDGE_TOKEN_REGEX.exec(line);
        if (match !== null) {
          parts.push(line.slice(segmentStart, i), match[0]);
          i += match[0].length;
          segmentStart = i;
          continue;
        }
      }
    }
    i += 1;
  }

  if (parts.length === 0) return null;
  parts.push(line.slice(segmentStart));
  return parts;
}

function repairEndpoint(endpoint: string, declared: DeclaredNodes): string {
  const label = endpoint.normalize("NFC").replace(/[ \t]+/g, " ");

  // Best repair: the text is the label of a node declared elsewhere in the
  // diagram - reference that node instead of inventing a duplicate.
  const declaredId = declared.labelToId.get(label);
  if (declaredId !== undefined) return declaredId;

  let nodeId = stripDiacritics(label).replace(/[^\p{L}\p{M}\p{N}_]+/gu, "_");
  // Never silently relabel an existing node that happens to share the
  // derived ID (mermaid keeps the last label it sees for an ID).
  while (declared.idToLabel.has(nodeId) && declared.idToLabel.get(nodeId) !== label) {
    nodeId += "_";
  }
  return quoteNodeLabel(nodeId, label);
}

/**
 * Rewrites a bare multi-word token used as an edge endpoint - a node label
 * referenced directly instead of through its declared ID, e.g.
 * `OpenSearch --> LLM Azure`. When a declared node carries exactly that
 * label, the reference is resolved to its ID; otherwise a deterministic safe
 * ID is generated with the original text as a quoted label:
 * `OpenSearch --> LLM_Azure["LLM Azure"]`.
 *
 * Flowcharts only: other diagram types (sequence, state) legitimately place
 * free text next to arrows.
 */
function repairBareMultiWordNodeRefs(code: string): string {
  const body = code.replace(FRONTMATTER_REGEX, "");
  if (!FLOWCHART_HEADER_REGEX.test(body)) return code;

  const declared = collectDeclaredNodes(code);

  return code
    .split("\n")
    .map((line) => {
      if (KEYWORD_LINE_REGEX.test(line) || line.trimStart().startsWith("%%")) return line;

      // A statement-terminating ";" is set aside so "A --> LLM Azure;" still
      // exposes a bare endpoint, then restored on the repaired line.
      const terminatorIndex = line.match(/;[ \t]*$/)?.index ?? line.length;
      const core = line.slice(0, terminatorIndex);

      const parts = splitOnEdgeTokens(core);
      if (parts === null) return line;

      const repaired = parts
        .map((part, index) => {
          const isEdgeToken = index % 2 === 1;
          if (isEdgeToken) return part;

          const endpoint = part.trim();
          if (!BARE_MULTI_WORD_NODE_REGEX.test(endpoint)) return part;

          const leadingLength = part.length - part.trimStart().length;
          const leading = part.slice(0, leadingLength);
          const trailing = part.slice(leadingLength + endpoint.length);
          return leading + repairEndpoint(endpoint, declared) + trailing;
        })
        .join("");

      return repaired + line.slice(terminatorIndex);
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

    return quoteNodeLabel(nodeId, label);
  });

  return repairBareMultiWordNodeRefs(withQuotedLabels);
}
