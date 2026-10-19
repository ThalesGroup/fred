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

import { fromMarkdown } from "mdast-util-from-markdown";

function escapeText(source: string): string {
  return source.replace(/(\\*)</g, (match, slashes: string) => (slashes.length % 2 === 0 ? `${slashes}\\<` : match));
}

export function sanitizeEditorMarkdown(markdown: string): string {
  if (!markdown.includes("<")) return markdown;

  // MDX parses Markdown inside HTML blocks. Disable only opaque HTML-flow nodes
  // so inline HTML tokens stay intact and Markdown code keeps its full context.
  const nodes = [...fromMarkdown(markdown, { extensions: [{ disable: { null: ["htmlFlow"] } }] }).children];
  const edits: { start: number; end: number; text: string }[] = [];
  for (const node of nodes) {
    const start = node.position?.start.offset;
    const end = node.position?.end.offset;
    if (start === undefined || end === undefined) continue;
    const source = markdown.slice(start, end);

    // MDX treats text '<' as JSX and disables Markdown's angle-bracket autolinks.
    // Use Markdown positions to preserve code, HTML, destinations and formatting.
    if (node.type === "text") {
      const text = escapeText(source);
      if (text !== source) edits.push({ start, end, text });
    } else if (node.type === "link" && source.startsWith("<")) {
      const label = source.slice(1, -1).replace(/([\\`*_{}\[\]<>~&])/g, "\\$1");
      const destination = node.url.replace(/([\\&<>])/g, "\\$1");
      edits.push({ start, end, text: `[${label}](<${destination}>)` });
    } else if (node.type === "image" || node.type === "imageReference") {
      // Image alt text has no child positions; parse its equivalent link label.
      const text = `!${sanitizeEditorMarkdown(source.slice(1))}`;
      if (text !== source) edits.push({ start, end, text });
    } else if ("children" in node) {
      nodes.push(...node.children);
    }
  }

  const chunks: string[] = [];
  let offset = 0;
  for (const edit of edits.sort((a, b) => a.start - b.start)) {
    chunks.push(markdown.slice(offset, edit.start), edit.text);
    offset = edit.end;
  }
  chunks.push(markdown.slice(offset));
  return chunks.join("");
}
