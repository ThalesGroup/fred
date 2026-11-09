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

import { forwardRef, useMemo, type AnchorHTMLAttributes } from "react";
import type { RawUiPart } from "@rework/types/parts";
import { MessageBubble } from "@shared/atoms/MessageBubble/MessageBubble";
import { ThinkingDots } from "@shared/atoms/ThinkingDots/ThinkingDots";
import { MarkdownRenderer } from "../MarkdownRenderer/MarkdownRenderer";
import { ArtifactLinkChip, conversationArtifactForHref } from "../ArtifactLinks/ArtifactLinkChip";

interface AssistantMessageProps {
  text: string;
  isStreaming: boolean;
  onSourceClick?: (index: number) => void;
  uiParts?: readonly RawUiPart[];
}

// Forwards to MarkdownRenderer's root so a caller (AssistantTurn's copy
// button) can read the rendered content directly instead of querying the DOM
// for it. Stays null while only ThinkingDots is rendered — same as before.
export const AssistantMessage = forwardRef<HTMLDivElement, AssistantMessageProps>(function AssistantMessage(
  { text, isStreaming, onSourceClick, uiParts },
  ref,
) {
  const linkRenderer = useMemo(() => {
    if (!uiParts?.length) return undefined;
    return function ArtifactLink({ href, children, title }: AnchorHTMLAttributes<HTMLAnchorElement>) {
      const artifact = href ? conversationArtifactForHref(href, uiParts) : undefined;
      return artifact ? (
        <ArtifactLinkChip link={artifact} title={title}>
          {children}
        </ArtifactLinkChip>
      ) : (
        <a href={href} title={title}>
          {children}
        </a>
      );
    };
  }, [uiParts]);

  if (!text && !isStreaming) return null;

  return (
    <MessageBubble role="assistant">
      {text ? (
        <MarkdownRenderer
          ref={ref}
          text={text}
          onSourceClick={onSourceClick}
          streaming={isStreaming}
          linkRenderer={linkRenderer}
        />
      ) : (
        <ThinkingDots />
      )}
    </MessageBubble>
  );
});
