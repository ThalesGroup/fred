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

import { MessageBubble } from "@shared/atoms/MessageBubble/MessageBubble";
import { ThinkingDots } from "@shared/atoms/ThinkingDots/ThinkingDots";
import { MarkdownRenderer } from "../MarkdownRenderer/MarkdownRenderer";

interface AssistantMessageProps {
  text: string;
  isStreaming: boolean;
  onSourceClick?: (index: number) => void;
}

export function AssistantMessage({ text, isStreaming, onSourceClick }: AssistantMessageProps) {
  if (!text && !isStreaming) return null;

  return (
    <MessageBubble role="assistant">
      {text ? (
        <MarkdownRenderer text={text} onSourceClick={onSourceClick} />
      ) : (
        <ThinkingDots />
      )}
    </MessageBubble>
  );
}
