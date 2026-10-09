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

import { memo, useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { skillInvocationsText } from "@rework/utils/skillInvocation";
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import { useCopyConfirmation } from "@hooks/useCopyConfirmation";
import { UserMessage } from "@shared/molecules/UserMessage/UserMessage";
import type { CommandDescriptor, SkillInvocation } from "../../../../../slices/runtime/runtimeOpenApi";
import { ActionBar } from "@shared/molecules/ActionBar/ActionBar";
import type { Action } from "@shared/molecules/ActionBar/ActionBar";
import styles from "./UserTurn.module.css";

interface UserTurnProps {
  text: string;
  /** Anchor for the outline rail: its marks scroll to this node, and the
   *  scroll-spy reads its position to say which turn is being read. */
  turnId?: string;
  /** Called when user clicks the edit action. If omitted, edit action is hidden. */
  onEdit?: (text: string) => void;
  /** Present when the turn was launched by a prompt command: the bubble then
   *  shows the command, and `onOpenCommand` reveals the text that was sent. */
  command?: CommandDescriptor | null;
  skillName?: SkillInvocation["name"] | null;
  skillNames?: SkillInvocation["name"][];
  skillDescriptions?: ReadonlyMap<string, string>;
  skillDescription?: string | null;
  onOpenSkill?: (name: string) => void;
  /** Takes the turn's own values rather than a closure, so the caller can
   *  hand down one stable callback for every row — an arrow built per message
   *  would defeat this component's memo on every streamed frame. */
  onOpenCommand?: (turn: { text: string; command: CommandDescriptor }) => void;
}

// Memoized alongside AssistantTurn — see #2221.
export const UserTurn = memo(function UserTurn({
  text,
  turnId,
  onEdit,
  command,
  skillName,
  skillNames,
  skillDescriptions,
  skillDescription,
  onOpenSkill,
  onOpenCommand,
}: UserTurnProps) {
  const { t } = useTranslation();
  const { copied, confirmCopied } = useCopyConfirmation();
  const invocationText = skillInvocationsText(text, skillNames ?? (skillName ? [skillName] : []), command);

  const openCommand = useCallback(() => {
    if (command && onOpenCommand) onOpenCommand({ text, command });
  }, [command, onOpenCommand, text]);

  const copyAction = useCallback(() => {
    // Same call AssistantTurn makes when it has no rendered node to serialise:
    // with no HTML, writeRichClipboard writes text/plain only — which is all a
    // user message ever is. It also absorbs both clipboard failure modes (a
    // denied permission rejects; a non-secure origin has no navigator.clipboard
    // at all, so the property access throws synchronously).
    writeRichClipboard("", invocationText).then((success) => {
      if (success) confirmCopied();
    });
  }, [invocationText, confirmCopied]);

  const actions: Action[] = useMemo(
    () => [
      ...(onEdit
        ? [{ id: "edit", icon: "edit", label: t("chatbot.editMessage"), onClick: () => onEdit(invocationText) }]
        : []),
      {
        id: "copy",
        icon: copied ? "check" : "content_copy",
        label: copied ? t("chatbot.copyMessage.copied") : t("chatbot.copyMessage.tooltip"),
        onClick: copyAction,
      },
    ],
    [onEdit, invocationText, copied, copyAction, t],
  );

  return (
    <div className={styles.turn} data-turn-id={turnId}>
      {/* Beside the bubble (user turns are right-aligned), revealed on hover. */}
      <ActionBar actions={actions} className={styles.actions} />
      <UserMessage
        text={text}
        command={command}
        skillNames={skillNames}
        skillDescriptions={skillDescriptions}
        skillName={skillName}
        skillDescription={skillDescription}
        onOpenSkill={onOpenSkill}
        onOpenCommand={command && onOpenCommand ? openCommand : undefined}
      />
    </div>
  );
});
