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

import { Fragment } from "react";
import { useTranslation } from "react-i18next";
import Chip from "@shared/atoms/Chip/Chip";
import Icon from "@shared/atoms/Icon/Icon";
import { fileIconSpec } from "@rework/utils/fileIconSpec";
import type { SessionAttachment } from "@rework/types/attachments";
import {
  findSkillInvocations,
  skillReferenceAt,
  skillInvocationsText,
  usablePromptList,
} from "@rework/utils/skillInvocation";
import { MessageBubble } from "@shared/atoms/MessageBubble/MessageBubble";
import { CommandTurn } from "@shared/molecules/CommandTurn/CommandTurn";
import { SkillBadge } from "@shared/molecules/SkillBadge/SkillBadge";
import type { CommandDescriptor, SkillInvocation } from "../../../../../slices/runtime/runtimeOpenApi";
import type { SkillSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./UserMessage.module.css";

interface UserMessageProps {
  text: string;
  /** Present when the turn was launched by a prompt command. `text` is still
   *  the full assembled text — it just does not belong in the chat body. */
  command?: CommandDescriptor | null;
  skillName?: SkillInvocation["name"] | null;
  skillNames?: SkillInvocation["name"][];
  skillInvocations?: SkillInvocation[];
  builtinSkillIds?: string[];
  skillSummaries?: ReadonlyMap<string, SkillSummary>;
  skillDescription?: string | null;
  onOpenSkill?: (name: string) => void;
  /** `promptIndex` is the entry of the turn's prompt list that was activated;
   *  absent for a turn that has no usable list. */
  onOpenCommand?: (promptIndex?: number) => void;
  /** Files placed on this message, shown read-only above the text. */
  attachments?: SessionAttachment[];
}

export function UserMessage({
  text,
  command,
  skillName,
  skillNames,
  skillInvocations,
  builtinSkillIds,
  skillSummaries,
  skillDescription,
  onOpenSkill,
  onOpenCommand,
  attachments,
}: UserMessageProps) {
  const { t } = useTranslation();
  const names = skillNames ?? (skillName ? [skillName] : []);
  const displayedText = skillInvocationsText(text, names, command);
  const skillTokens = findSkillInvocations(displayedText, names).map((token) => ({
    ...token,
    reference: skillReferenceAt(skillInvocations, token),
    kind: "skill" as const,
  }));
  const listed = usablePromptList(command, text);
  const singleToken =
    !listed && command && (command.draft_text != null || names.length)
      ? findSkillInvocations(displayedText, [command.command]).find((token) =>
          command.draft_text == null
            ? token.from === 0
            : command.draft_command_offset == null || token.from === command.draft_command_offset,
        )
      : undefined;
  // One badge per listed prompt; a turn without a usable list keeps its single one.
  const promptTokens = listed
    ? listed.map((entry, index) => ({
        kind: "prompt" as const,
        name: entry.command,
        from: entry.draft_offset,
        to: entry.draft_offset + entry.command.length + 1,
        shown: entry,
        index,
      }))
    : singleToken && command
      ? [{ ...singleToken, kind: "prompt" as const, shown: command, index: undefined }]
      : [];
  const tokens = [
    ...skillTokens.filter((token) => !promptTokens.some((prompt) => prompt.from === token.from)),
    ...promptTokens,
  ].sort((a, b) => a.from - b.from);
  return (
    <MessageBubble role="user">
      {attachments && attachments.length > 0 && (
        <ul className={styles.attachments} aria-label={t("chatbot.attachmentChip.ariaLabel")}>
          {attachments.map((attachment) => (
            <li key={attachment.attachmentId}>
              <Chip
                appearance="tonal"
                label={attachment.name}
                leading={<Icon category="outlined" type={fileIconSpec(attachment.name, attachment.mime).type} />}
              />
            </li>
          ))}
        </ul>
      )}
      {tokens.length ? (
        <div className={styles.skillTurn} data-skill-message>
          {tokens.map((token, index) => (
            <Fragment key={token.from}>
              {displayedText.slice(index ? tokens[index - 1].to : 0, token.from)}
              {token.kind === "prompt" ? (
                <CommandTurn
                  command={token.shown}
                  inline
                  onOpen={onOpenCommand && (() => onOpenCommand(token.index))}
                />
              ) : (
                <SkillBadge
                  name={token.name}
                  builtin={
                    skillSummaries?.get(token.reference?.skill_id ?? "")?.builtin ??
                    builtinSkillIds?.includes(token.reference?.skill_id ?? "")
                  }
                  description={
                    skillSummaries?.get(token.reference?.skill_id ?? "")?.description ?? skillDescription ?? undefined
                  }
                  spaceName={skillSummaries?.get(token.reference?.skill_id ?? "")?.space_name}
                  onOpen={onOpenSkill && token.reference ? () => onOpenSkill(token.reference!.skill_id) : undefined}
                />
              )}
            </Fragment>
          ))}
          {displayedText.slice(tokens[tokens.length - 1].to)}
        </div>
      ) : command && !command.draft_text ? (
        <CommandTurn command={command} onOpen={onOpenCommand && (() => onOpenCommand())} />
      ) : (
        <p className={styles.text}>{displayedText}</p>
      )}
    </MessageBubble>
  );
}
