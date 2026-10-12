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

import { useCallback, useMemo, useState } from "react";
import type { CommandKeyEvent } from "@shared/molecules/RichInputField/RichInputField";
import { skillInvocationsText } from "@rework/utils/skillInvocation";
import type { ThreadMessage } from "@rework/types/thread";

/** The line the person typed: a command turn stores the expanded prompt as its text. */
export function recallLineOf(message: ThreadMessage): string {
  const { command } = message;
  if (command?.draft_text != null) return command.draft_text;
  const names = message.skillNames ?? (message.skillName ? [message.skillName] : []);
  if (!command || names.length) return skillInvocationsText(message.text, names, command).trim();
  return command.appended_text ? `/${command.command} ${command.appended_text}` : `/${command.command}`;
}

/** Sent turns newest first, collapsing only repetitions with the same invocation. */
function recallTurnsOf(messages: ThreadMessage[]): { line: string; message: ThreadMessage }[] {
  const turns: { line: string; message: ThreadMessage }[] = [];
  let previousIdentity: string | null = null;
  for (let i = messages.length - 1; i >= 0; i--) {
    const message = messages[i];
    if (message.role !== "user") continue;
    const line = recallLineOf(message);
    const identity = JSON.stringify([
      line,
      message.command?.prompt_id ?? null,
      message.command?.draft_command_offset ?? null,
      message.skillNames ?? (message.skillName ? [message.skillName] : []),
    ]);
    if (!line || identity === previousIdentity) continue;
    turns.push({ line, message });
    previousIdentity = identity;
  }
  return turns;
}

export function recallLinesOf(messages: ThreadMessage[]): string[] {
  return recallTurnsOf(messages).map((turn) => turn.line);
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
  onRecall: (line: string, message?: ThreadMessage) => void;
}): (event: CommandKeyEvent) => boolean {
  const { messages, input, menuOpen, disabled, onRecall } = params;
  const turns = useMemo(() => recallTurnsOf(messages), [messages]);
  // Index into `turns` of the shown entry. It only counts while the composer
  // still holds that exact line, so no change handler is needed to end browsing.
  const [index, setIndex] = useState<number | null>(null);
  const shown = index !== null && turns[index]?.line === input ? index : null;

  return useCallback(
    (event: CommandKeyEvent): boolean => {
      if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return false;
      if (disabled || menuOpen || event.nativeEvent.isComposing) return false;
      if (event.shiftKey || event.ctrlKey || event.altKey || event.metaKey) return false;
      if (shown === null && input !== "") return false;

      if (event.key === "ArrowUp") {
        if (turns.length === 0) return false;
        event.preventDefault();
        const next = shown === null ? 0 : Math.min(shown + 1, turns.length - 1);
        if (next !== shown) {
          setIndex(next);
          onRecall(turns[next].line, turns[next].message);
        }
        return true;
      }

      if (shown === null) return false;
      event.preventDefault();
      const next = shown - 1;
      setIndex(next < 0 ? null : next);
      onRecall(next < 0 ? "" : turns[next].line, next < 0 ? undefined : turns[next].message);
      return true;
    },
    [disabled, menuOpen, shown, input, turns, onRecall],
  );
}
