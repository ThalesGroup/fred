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

import Mermaid from "./Mermaid.tsx"; // adjust path if needed
import { Theme } from "@mui/material";

interface GetMarkdownComponentsOptions {
  theme: Theme;
  size: "small" | "medium" | "large";
  enableEmojiFix?: boolean;
}

/**
 * GetMarkdownComponents
 *
 * A factory function that returns a mapping of custom React components
 * to be used with `react-markdown` for rendering markdown content.
 *
 * This function supports:
 * - Dynamic theming based on MUI's `theme.typography.markdown` styles
 * - Font size scaling (`small`, `medium`, `large`)
 * - Optional emoji fix for emphasis or stage direction rendering (e.g., disables italics on emojis)
 * - Mermaid diagram rendering from fenced code blocks (```mermaid)
 *
 * It is designed to be used in markdown-rendering UIs like chat messages,
 * documentation viewers, or markdown previews.
 *
 * ---
 *
 * Usage Example:
 * ```tsx
 * import ReactMarkdown from "react-markdown";
 * import { useTheme } from "@mui/material";
 * import { GetMarkdownComponents } from "./GetMarkdownComponents";
 *
 * const theme = useTheme();
 * const components = GetMarkdownComponents({ theme, size: "small" });
 *
 * <ReactMarkdown components={components}>{markdownText}</ReactMarkdown>
 * ```
 *
 * ---
 *
 * @param {Object} options
 * @param {Theme} options.theme - MUI theme object, used for consistent typography.
 * @param {'small' | 'medium' | 'large'} options.size - Controls font size scaling.
 * @param {boolean} [options.enableEmojiFix=true] - When true, disables italics on <em> and <p> to improve emoji rendering.
 *
 * @returns {Object} Components map to be passed to `react-markdown`.
 */
export function getMarkdownComponents({ theme, size, enableEmojiFix = true }: GetMarkdownComponentsOptions) {
  const baseStyle = (style: any) => (size === "small" ? { ...style, fontSize: "0.85rem" } : style);

  return {
    h1: ({ node, ...props }) => <h1 style={baseStyle(theme.typography.markdown.h1)} {...props} />,
    h2: ({ node, ...props }) => <h2 style={baseStyle(theme.typography.markdown.h2)} {...props} />,
    h3: ({ node, ...props }) => <h3 style={baseStyle(theme.typography.markdown.h3)} {...props} />,
    h4: ({ node, ...props }) => <h4 style={baseStyle(theme.typography.markdown.h4)} {...props} />,
    p: ({ node, ...props }) => (
      <p
        style={{
          fontStyle: enableEmojiFix ? "normal" : undefined,
          ...baseStyle(theme.typography.markdown.p),
        }}
        {...props}
      />
    ),
    em: ({ node, ...props }) => (
      <em
        style={{
          fontStyle: enableEmojiFix ? "normal" : undefined,
        }}
        {...props}
      />
    ),
    a: ({ node, ...props }) => <a style={baseStyle(theme.typography.markdown.a)} {...props} />,
    ul: ({ node, ...props }) => <ul style={baseStyle(theme.typography.markdown.ul)} {...props} />,
    li: ({ node, ...props }) => <li style={baseStyle(theme.typography.markdown.li)} {...props} />,
    code: ({ node, inline, className, children, ...props }) => {
      const isMermaid = /language-mermaid/.test(className || "");
      if (isMermaid && children) {
        return <Mermaid code={String(children).replace(/\n$/, "")} />;
      }
      return (
        <code style={baseStyle(theme.typography.markdown.code)} {...props}>
          {children}
        </code>
      );
    },
  };
}
