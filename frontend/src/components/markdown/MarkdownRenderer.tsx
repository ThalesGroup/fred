import { useTheme } from "@mui/material";
import ReactMarkdown from "react-markdown";
import { getMarkdownComponents } from "./GetMarkdownComponents";

export interface MarkdownRendererProps {
  content: string;
  size?: 'small' | 'medium' | 'large';
  enableEmojiSubstitution?: boolean;
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
 *
 * @returns {JSX.Element} A React component that renders styled markdown content.
 */
export default function MarkdownRenderer({
  content,
  size = "medium",
  enableEmojiSubstitution = false,
}: MarkdownRendererProps) {
  const theme = useTheme();
  const components = getMarkdownComponents({ theme, size, enableEmojiFix: true });
  const finalContent = enableEmojiSubstitution ? replaceStageDirectionsWithEmoji(content || "") : (content || "No markdown content provided.");

  return <ReactMarkdown components={components}>{finalContent}</ReactMarkdown>;
}
