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

import remarkDirective from "remark-directive";
import MarkdownRenderer, { MarkdownRendererProps } from "./MarkdownRenderer";
import { alpha, Box, Typography, useTheme } from "@mui/material";

import type { Plugin } from "unified";
import { visit } from "unist-util-visit";

// Highlight class names
export const HIGHLIGHT_BLOCK_CLASS = "highlight";
export const HIGHLIGHT_INLINE_CLASS = "inline-highlight";

// Plugin to handle custom highlight directives
// This allows us to use `:::highlight` for block-level highlights
// and `:highlight[...text...]` for inline highlights
export const highlightDirective: Plugin = () => {
  return (tree) => {
    visit(tree, (node: any) => {
      if (node.type === "containerDirective" && node.name === "highlight") {
        node.data = node.data || {};
        node.data.hName = "div";
        node.data.hProperties = { className: HIGHLIGHT_BLOCK_CLASS };
      }

      if (node.type === "textDirective" && node.name === "highlight") {
        node.data = node.data || {};
        node.data.hName = "span";
        node.data.hProperties = { className: HIGHLIGHT_INLINE_CLASS };
      }
    });
  };
};

export type HighlightedPart = {
  start: number;
  end: number;
};

export interface MarkdownRendererWithHighlightsProps extends MarkdownRendererProps {
  highlightedParts: HighlightedPart[];
}

export default function MarkdownRendererWithHighlights({
  highlightedParts,
  content,
  remarkPlugins = [],
  components: userComponents,
  ...props
}: MarkdownRendererWithHighlightsProps) {
  const theme = useTheme();
  let highlightedContent = content;
  if (highlightedParts && highlightedParts.length > 0 && highlightedContent) {
    // Sort by start index to process in order
    const sortedParts = [...highlightedParts].sort((a, b) => a.start - b.start);
    let result = "";
    let lastIndex = 0;
    for (const { start, end } of sortedParts) {
      // Clamp indices to content length
      const safeStart = Math.max(0, Math.min(start, highlightedContent.length));
      const safeEnd = Math.max(safeStart, Math.min(end, highlightedContent.length));

      // Add text between highlighted parts
      result += highlightedContent.slice(lastIndex, safeStart);

      // Add highlighted part: use container directive if multi-line, else text directive
      const part = highlightedContent.slice(safeStart, safeEnd);
      if (/\n/.test(part)) {
        // Block-level highlight
        result += `\n:::highlight\n${part}\n:::\n`;
      } else {
        // Inline highlight
        result += `:highlight[${part}]`;
      }
      lastIndex = safeEnd;
    }
    result += highlightedContent.slice(lastIndex);
    highlightedContent = result;
  }

  // Custom highlight components
  const highlightComponents = {
    div: ({ node, children, ...props }) => {
      const { ref, className, ...rest } = props;
      if (!className || !className.includes(HIGHLIGHT_BLOCK_CLASS)) {
        return (
          <div className={className} {...rest}>
            {children}
          </div>
        );
      }
      return (
        <Box
          sx={{
            bgcolor: alpha(theme.palette.primary.main, 0.2),
            border: `2px solid ${theme.palette.primary.main}`,
            borderRadius: 1,
            padding: 1,
            my: 2,
          }}
          className={className}
          {...rest}
        >
          {children}
        </Box>
      );
    },
    span: ({ node, children, ...props }) => {
      const { ref, className, ...rest } = props;
      if (!className || !className.includes(HIGHLIGHT_INLINE_CLASS)) {
        return (
          <span className={className} {...rest}>
            {children}
          </span>
        );
      }
      return (
        <Typography
          component="span"
          sx={{
            bgcolor: alpha(theme.palette.primary.main, 0.5),
            px: 0.5,
            borderRadius: 0.5,
          }}
          className={className}
          {...rest}
        >
          {children}
        </Typography>
      );
    },
  };

  return (
    <MarkdownRenderer
      {...props}
      content={highlightedContent}
      remarkPlugins={[remarkDirective, highlightDirective, ...remarkPlugins]}
      components={{ ...highlightComponents, ...(userComponents || {}) }}
    />
  );
}
