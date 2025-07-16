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

import { useTheme } from "@mui/material";
import ReactMarkdown, { type Components } from "react-markdown";
import type { PluggableList } from "unified";
import { getMarkdownComponents } from "./GetMarkdownComponents";
import remarkGfm from "remark-gfm";

export interface MarkdownRendererProps {
  content: string;
  size?: "small" | "medium" | "large";
  enableEmojiSubstitution?: boolean;
  remarkPlugins?: PluggableList;
  components?: Components;
}

function replaceStageDirectionsWithEmoji(text: string): string {
  return text
    .replace(/\badjusts glasses\b/gi, "🤓")
    .replace(/\bsmiles\b/gi, "😶")
    .replace(/\bshrugs\b/gi, "🤷")
    .replace(/\bnods\b/gi, "👍")
    .replace(/\blaughs\b/gi, "😂")
    .replace(/\bsighs\b/gi, "😮‍💨")
    .replace(/\bgrins\b/gi, "😁")
    .replace(/\bwinks\b/gi, "😉")
    .replace(/\bclears throat\b/gi, "😶‍🌫️");
}
/**
 * MarkdownRenderer
 *
 * A lightweight wrapper around `react-markdown` that provides consistent, theme-aware
 * markdown rendering across your application, with optional customization for chat-like use cases.
 *
 * Features:
 * - Applies MUI theme-based typography styles via `getMarkdownComponents`
 * - Supports size scaling (`small`, `medium`, `large`)
 * - Optionally replaces common stage directions with emojis for conversational rendering
 * - Automatically supports mermaid diagrams (```mermaid blocks)
 *
 * ---
 *
 * Example usage:
 * ```tsx
 * <MarkdownRenderer content="**Hello** _world_!" size="small" />
 * ```
 *
 * ---
 *
 * @param {string} content - Markdown string to render.
 * @param {'small' | 'medium' | 'large'} [size='medium'] - Optional size control for font scaling.
 * @param {boolean} [enableEmojiSubstitution=false] - If true, replaces stage directions like "shrugs" or "smiles" with emojis.
 * @param {PluggableList} [remarkPlugins] - Optional list of remark plugins to customize markdown parsing and rendering.
 * @param {Components} [components] - Optional custom components to override default markdown rendering.
 *
 * @returns {JSX.Element} A React component that renders styled markdown content.
 */
export default function MarkdownRenderer({
  content,
  size = "medium",
  enableEmojiSubstitution = false,
  remarkPlugins,
  ...props
}: MarkdownRendererProps) {
  const theme = useTheme();
  const components = getMarkdownComponents({
    theme,
    size,
    enableEmojiFix: true,
  });
  const finalContent = enableEmojiSubstitution
    ? replaceStageDirectionsWithEmoji(content || "")
    : content || "No markdown content provided.";

  return (
    <ReactMarkdown
      skipHtml={true}
      components={{
        ...components,
        ...(props.components || {}),
      }}
      remarkPlugins={[remarkGfm, ...remarkPlugins]}
    >
      {finalContent}
    </ReactMarkdown>
  );
}
