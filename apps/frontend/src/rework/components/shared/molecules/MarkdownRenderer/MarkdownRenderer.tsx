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

import { useMemo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import remarkDirective from "remark-directive";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { CodeBlock } from "../CodeBlock/CodeBlock";
import { MindMapBlock } from "../MindMapBlock";
import { MermaidBlock } from "../MermaidBlock/MermaidBlock";
import { SourceBadge } from "../../atoms/SourceBadge/SourceBadge";
import styles from "./MarkdownRenderer.module.css";
import { getStreamingMarkdownState, type PendingStreamingFence } from "./streamingGuard";

interface MarkdownRendererProps {
  text: string;
  onSourceClick?: (index: number) => void;
  streaming?: boolean;
}

interface MdastNode {
  type: string;
  name?: string;
  children?: MdastNode[];
  data?: Record<string, unknown>;
}

interface HastNode {
  type: string;
  tagName?: string;
  children?: HastNode[];
  properties?: Record<string, unknown>;
  value?: string;
}

/**
 * Remark plugin: map :::details[Title] container directives to native
 * <details><summary> elements via hast data properties.
 * Must run after remarkDirective (which parses the directive syntax).
 */
function remarkDetailsDirective() {
  return (tree: MdastNode) => {
    walkMdast(tree, (node: MdastNode) => {
      if (node.type !== "containerDirective" || node.name !== "details") return;
      node.data = { ...node.data, hName: "details" };
      const label = node.children?.find((c: MdastNode) => c.type === "directiveLabel");
      if (label) {
        label.data = { ...label.data, hName: "summary" };
      }
    });
  };
}

function walkMdast(node: MdastNode, visitor: (n: MdastNode) => void) {
  visitor(node);
  if (Array.isArray(node.children)) {
    for (const child of node.children) walkMdast(child, visitor);
  }
}

/**
 * Rehype plugin: transform [N] text patterns into <sup class="fred-cite" data-n="N">
 * elements in the hast tree before sanitization. Skips code/pre/kbd/samp nodes.
 * Does not depend on unist-util-visit — uses a plain recursive tree rebuild.
 */
function rehypeCitations() {
  const SKIP_TAGS = new Set(["code", "pre", "kbd", "samp"]);
  const RE = /\[(\d+)\]/g;

  function processChildren(children: HastNode[], parentTagName?: string): HastNode[] {
    if (parentTagName && SKIP_TAGS.has(parentTagName)) return children;

    const result: HastNode[] = [];
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

  return (tree: { children?: HastNode[] }) => {
    if (tree.children) {
      tree.children = processChildren(tree.children);
    }
  };
}

// Sanitize schema extended once at module level — never recreated.
// - className added to global (*): rehype-sanitize strips it by default, which
//   breaks KaTeX layout (CSS targets .katex/.base/… class selectors) and
//   language detection on fenced code blocks (language-python class stripped).
// - style on span: KaTeX uses inline styles for vertical positioning
// - data-n on sup: citation badges injected by rehypeCitations
// - details + summary: native collapsible from :::details directives
const sanitizeSchema = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), "details", "summary"],
  attributes: {
    ...defaultSchema.attributes,
    "*": [...(defaultSchema.attributes?.["*"] ?? []), "className"],
    span: [...(defaultSchema.attributes?.span ?? []), "style"],
    sup: [...(defaultSchema.attributes?.sup ?? []), "data-n"],
  },
};

// Plugin arrays are module-level constants so ReactMarkdown receives stable
// references across renders — avoids re-parsing the full content on every
// streaming delta.
const REMARK_PLUGINS: Parameters<typeof ReactMarkdown>[0]["remarkPlugins"] = [
  remarkMath,
  remarkGfm,
  remarkDirective,
  remarkDetailsDirective,
];

const REHYPE_PLUGINS: Parameters<typeof ReactMarkdown>[0]["rehypePlugins"] = [
  rehypeCitations,
  [rehypeKatex, { output: "html" }],
  [rehypeSanitize, sanitizeSchema],
];

export function MarkdownRenderer({ text, onSourceClick, streaming = false }: MarkdownRendererProps) {
  const { stableMarkdown, pendingFence } = useMemo(
    () => (streaming ? getStreamingMarkdownState(text) : { stableMarkdown: text, pendingFence: null }),
    [streaming, text],
  );

  // Stable reference across renders — prevents react-markdown from treating
  // component functions as new types on every render, which would remount block
  // components (MermaidBlock, CodeBlock) and cause their effects to re-fire.
  const components = useMemo(
    () => ({
      // Pass-through pre: CodeBlock provides its own wrapper
      pre({ children }: { children: React.ReactNode }) {
        return <>{children}</>;
      },
      // code: mindmap/mermaid fences → custom blocks; other fenced blocks → CodeBlock; inline → CodeBlock inline
      code({ className, children }: { className?: string; children?: React.ReactNode }) {
        const lang = /language-([\w-]+)/.exec(className || "")?.[1];
        if (lang === "mindmap" || lang === "mindmap-json") {
          return <MindMapBlock code={String(children).replace(/\n$/, "")} language={lang} />;
        }
        if (lang === "mermaid") {
          return <MermaidBlock code={String(children).replace(/\n$/, "")} />;
        }
        if (className) {
          return <CodeBlock code={String(children).replace(/\n$/, "")} language={lang} />;
        }
        return <CodeBlock code={String(children)} inline />;
      },
      // hr: suppress horizontal rules — visual noise in a chat context
      hr: () => null,
      // sup: citation badges injected by rehypeCitations → SourceBadge
      sup({ children, ...props }: React.HTMLAttributes<HTMLElement>) {
        const n = (props as Record<string, unknown>)["data-n"];
        if (n !== undefined && onSourceClick) {
          return <SourceBadge index={Number(n)} onClick={() => onSourceClick(Number(n))} />;
        }
        return <sup {...props}>{children}</sup>;
      },
    }),
    [onSourceClick],
  );

  function pendingFenceLanguage(fence: PendingStreamingFence): string {
    if (fence.kind === "code") {
      return fence.label ?? "plaintext";
    }
    if (fence.kind === "math") {
      return "math";
    }
    return fence.label ?? "directive";
  }

  function pendingFenceStreamingLabel(fence: PendingStreamingFence): string {
    if (fence.kind === "code") {
      return fence.label === "mermaid" ? "Generating Mermaid code..." : "Generating code block...";
    }
    if (fence.kind === "math") {
      return "Generating math block...";
    }
    return "Generating directive block...";
  }

  function renderPendingFence(fence: PendingStreamingFence | null) {
    if (fence === null) {
      return null;
    }

    return (
      <CodeBlock
        code={fence.content}
        language={pendingFenceLanguage(fence)}
        streaming
        streamingLabel={pendingFenceStreamingLabel(fence)}
      />
    );
  }

  return (
    <div className={styles.root}>
      {stableMarkdown ? (
        <ReactMarkdown remarkPlugins={REMARK_PLUGINS} rehypePlugins={REHYPE_PLUGINS} components={components}>
          {stableMarkdown}
        </ReactMarkdown>
      ) : null}
      {renderPendingFence(pendingFence)}
    </div>
  );
}
