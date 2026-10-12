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

import { useCallback, useMemo, useState, type KeyboardEvent } from "react";
import type { ThreadMessage } from "@rework/types/thread";

/** The line the person typed: a command turn stores the expanded prompt as its text. */
export function recallLineOf(message: ThreadMessage): string {
  const { command } = message;
  if (!command) return message.text.trim();
  return command.appended_text ? `/${command.command} ${command.appended_text}` : `/${command.command}`;
}

/** Sent lines of the conversation, newest first, consecutive repeats collapsed. */
export function recallLinesOf(messages: ThreadMessage[]): string[] {
  const lines: string[] = [];
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role !== "user") continue;
    const line = recallLineOf(messages[i]);
    if (line && line !== lines[lines.length - 1]) lines.push(line);
  }
  return lines;
}

/**
 * ArrowUp / ArrowDown browse the sent messages from an empty composer, as long
 * as the recalled line stays untouched: any edit hands the arrows back to the
 * caret. Same contract as the command trigger's `onKeyDown`.
 */
export function useComposerRecall(params: {
  messages: ThreadMessage[];
  input: string;
  menuOpen: boolean;
  disabled: boolean;
  onRecall: (line: string) => void;
}): (event: KeyboardEvent<HTMLTextAreaElement>) => boolean {
  const { messages, input, menuOpen, disabled, onRecall } = params;
  const lines = useMemo(() => recallLinesOf(messages), [messages]);
  // Index into `lines` of the shown entry. It only counts while the composer
  // still holds that exact line, so no change handler is needed to end browsing.
  const [index, setIndex] = useState<number | null>(null);
  const shown = index !== null && lines[index] === input ? index : null;

  return useCallback(
    (event: KeyboardEvent<HTMLTextAreaElement>): boolean => {
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return false;
      if (disabled || menuOpen || event.nativeEvent.isComposing) return false;
      if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return false;
      if (shown === null && input !== "") return false;

      if (event.key === "ArrowUp") {
        if (lines.length === 0) return false;
        event.preventDefault();
        const next = shown === null ? 0 : Math.min(shown + 1, lines.length - 1);
        if (next !== shown) {
          setIndex(next);
          onRecall(lines[next]);
        }
        return true;
      }

      if (shown === null) return false;
      event.preventDefault();
      const next = shown - 1;
      setIndex(next < 0 ? null : next);
      onRecall(next < 0 ? "" : lines[next]);
      return true;
    },
    [disabled, menuOpen, shown, input, lines, onRecall],
  );
}
