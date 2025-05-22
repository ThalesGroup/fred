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

/**
 * MarkdownViewer
 * 
 * A higher-level container component that wraps MarkdownRenderer and handles layout,
 * scrolling, and loading behavior.
 * 
 * It is useful in any context where markdown content may be loaded asynchronously and
 * needs to be displayed inside a scrollable panel or box with consistent padding and
 * background styling.
 * 
 * This component is responsible for:
 * - Showing a loading spinner while data is being fetched (`isLoading`)
 * - Providing a scrollable container (`overflow: auto`)
 * - Applying consistent layout styling (padding, background, border radius)
 * 
 * Props:
 * - markdown: The markdown string to render.
 * - isLoading: Whether to display a loading indicator instead of the content.
 * 
 * Usage:
 * ```tsx
 * <MarkdownViewer markdown={myMarkdownString} isLoading={isFetching} />
 * ```
 * 
 * For markdown rendering without layout or loading concerns, use MarkdownRenderer directly.
 */

import { Box, CircularProgress } from "@mui/material";
import MarkdownRenderer from "./MarkdownRenderer";

interface MarkdownViewerProps {
  markdown: string;
  isLoading?: boolean;
  size?: 'small' | 'medium' | 'large';
  enableEmojiSubstitution?: boolean;
}

const MarkdownViewer = ({
  markdown,
  isLoading = false,
  size = 'medium',
  enableEmojiSubstitution = false,
}: MarkdownViewerProps) => {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ flex: 1, overflow: 'auto', p: 3, bgcolor: 'background.paper', borderRadius: 1 }}>
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <CircularProgress />
          </Box>
        ) : (
          <MarkdownRenderer content={markdown} size={size} enableEmojiSubstitution={enableEmojiSubstitution} />
        )}
      </Box>
    </Box>
  );
};

export default MarkdownViewer;
