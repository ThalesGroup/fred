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

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { CodeBlock } from "../CodeBlock/CodeBlock";
import { SourceBadge } from "../../atoms/SourceBadge/SourceBadge";
import styles from "./MarkdownRenderer.module.css";

interface MarkdownRendererProps {
  text: string;
  onSourceClick?: (index: number) => void;
}

/**
 * Rehype plugin: transform [N] text patterns into <sup class="fred-cite" data-n="N">
 * elements in the hast tree before sanitization. Skips code/pre/kbd/samp nodes.
 * Does not depend on unist-util-visit — uses a plain recursive tree rebuild.
 */
function rehypeCitations() {
  const SKIP_TAGS = new Set(["code", "pre", "kbd", "samp"]);
  const RE = /\[(\d+)\]/g;

  function processChildren(children: any[], parentTagName?: string): any[] {
    if (parentTagName && SKIP_TAGS.has(parentTagName)) return children;

    const result: any[] = [];
    for (const child of children) {
      if (child.type === "element" && child.children) {
        result.push({ ...child, children: processChildren(child.children, child.tagName) });
      } else if (child.type === "text") {
        RE.lastIndex = 0;
        if (!RE.test(child.value)) {
          result.push(child);
          continue;
        }
        RE.lastIndex = 0;
        let last = 0;
        let m: RegExpExecArray | null;
        while ((m = RE.exec(child.value)) !== null) {
          if (m.index > last) result.push({ type: "text", value: child.value.slice(last, m.index) });
          result.push({
            type: "element",
            tagName: "sup",
            properties: { className: ["fred-cite"], "data-n": m[1] },
            children: [{ type: "text", value: `[${m[1]}]` }],
          });
          last = m.index + m[0].length;
        }
        if (last < child.value.length) result.push({ type: "text", value: child.value.slice(last) });
      } else {
        result.push(child);
      }
    }
    return result;
  }

  return (tree: any) => {
    if (tree.children) {
      tree.children = processChildren(tree.children);
    }
  };
}

// Extend default sanitize schema to allow data-n on sup (used by citation badges).
const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    sup: [...(defaultSchema.attributes?.sup ?? []), "data-n"],
  },
};

export function MarkdownRenderer({ text, onSourceClick }: MarkdownRendererProps) {
  return (
    <div className={styles.root}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeCitations, [rehypeSanitize, sanitizeSchema]]}
        components={{
          // Pass-through pre: CodeBlock provides its own wrapper
          pre({ children }) {
            return <>{children}</>;
          },
          // code: fenced blocks (have className) → CodeBlock; inline → CodeBlock inline
          code({ className, children }) {
            const lang = /language-(\w+)/.exec(className || "")?.[1];
            if (className) {
              return <CodeBlock code={String(children).replace(/\n$/, "")} language={lang} />;
            }
            return <CodeBlock code={String(children)} inline />;
          },
          // sup: citation badges injected by rehypeCitations → SourceBadge
          sup({ children, ...props }) {
            const n = (props as Record<string, unknown>)["data-n"];
            if (n !== undefined && onSourceClick) {
              return <SourceBadge index={Number(n)} onClick={() => onSourceClick(Number(n))} />;
            }
            return <sup {...props}>{children}</sup>;
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
