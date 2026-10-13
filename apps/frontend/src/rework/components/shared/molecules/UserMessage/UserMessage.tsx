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
import { findSkillInvocations, skillInvocationsText } from "@rework/utils/skillInvocation";
import { MessageBubble } from "@shared/atoms/MessageBubble/MessageBubble";
import { CommandTurn } from "@shared/molecules/CommandTurn/CommandTurn";
import { SkillBadge } from "@shared/molecules/SkillBadge/SkillBadge";
import type { CommandDescriptor, SkillInvocation } from "../../../../../slices/runtime/runtimeOpenApi";
import styles from "./UserMessage.module.css";

interface UserMessageProps {
  text: string;
  /** Present when the turn was launched by a prompt command. `text` is still
   *  the full assembled text — it just does not belong in the chat body. */
  command?: CommandDescriptor | null;
  skillName?: SkillInvocation["name"] | null;
  skillNames?: SkillInvocation["name"][];
  skillDescriptions?: ReadonlyMap<string, string>;
  skillDescription?: string | null;
  onOpenSkill?: (name: string) => void;
  onOpenCommand?: () => void;
}

export function UserMessage({
  text,
  command,
  skillName,
  skillNames,
  skillDescriptions,
  skillDescription,
  onOpenSkill,
  onOpenCommand,
}: UserMessageProps) {
  const names = skillNames ?? (skillName ? [skillName] : []);
  const displayedText = skillInvocationsText(text, names, command);
  const skillTokens = findSkillInvocations(displayedText, names).map((token) => ({ ...token, kind: "skill" as const }));
  const promptToken =
    command && (command.draft_text != null || names.length)
      ? findSkillInvocations(displayedText, [command.command]).find((token) =>
          command.draft_text == null
            ? token.from === 0
            : command.draft_command_offset == null || token.from === command.draft_command_offset,
        )
      : undefined;
  const tokens = [
    ...skillTokens.filter((token) => token.from !== promptToken?.from),
    ...(promptToken ? [{ ...promptToken, kind: "prompt" as const }] : []),
  ].sort((a, b) => a.from - b.from);
  return (
    <MessageBubble role="user">
      {tokens.length ? (
        <div className={styles.skillTurn} data-skill-message>
          {tokens.map((token, index) => (
            <Fragment key={token.from}>
              {displayedText.slice(index ? tokens[index - 1].to : 0, token.from)}
              {token.kind === "prompt" && command ? (
                <CommandTurn command={command} inline onOpen={onOpenCommand} />
              ) : (
                <SkillBadge
                  name={token.name}
                  description={skillDescriptions?.get(token.name) ?? skillDescription ?? undefined}
                  onOpen={onOpenSkill}
                />
              )}
            </Fragment>
          ))}
          {displayedText.slice(tokens[tokens.length - 1].to)}
        </div>
      ) : command && !command.draft_text ? (
        <CommandTurn command={command} onOpen={onOpenCommand} />
      ) : (
        <p className={styles.text}>{displayedText}</p>
      )}
    </MessageBubble>
  );
}
