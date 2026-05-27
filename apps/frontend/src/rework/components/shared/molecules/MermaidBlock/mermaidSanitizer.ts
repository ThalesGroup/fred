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

/**
 * Best-effort Mermaid sanitizer for common LLM formatting issues.
 *
 * Why it exists:
 * Mermaid parsing is strict for node labels and line-break syntax. LLM outputs
 * often contain literal backslash-n sequences and unquoted labels that include
 * parser-sensitive text like parentheses.
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

  return withBreakTags.replace(NODE_LABEL_REGEX, (_full, nodeId: string, innerLabel: string) => {
    const label = innerLabel.trim();
    if (!label) return _full;

    const isAlreadyQuoted =
      (label.startsWith('"') && label.endsWith('"')) || (label.startsWith("'") && label.endsWith("'"));

    if (isAlreadyQuoted) return _full;

    const needsQuotes = /<br\s*\/?>/i.test(label) || /[()]/.test(label);
    if (!needsQuotes) return _full;

    return `${nodeId}["${label.replace(/"/g, "&quot;")}"]`;
  });
}
