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
import { CommandTurn } from "@shared/molecules/CommandTurn/CommandTurn";
import type { CommandDescriptor } from "../../../../../slices/runtime/runtimeOpenApi";
import styles from "./UserMessage.module.css";

interface UserMessageProps {
  text: string;
  /** Present when the turn was launched by a prompt command. `text` is still
   *  the full assembled text — it just does not belong in the chat body. */
  command?: CommandDescriptor | null;
  onOpenCommand?: () => void;
}

export function UserMessage({ text, command, onOpenCommand }: UserMessageProps) {
  return (
    <MessageBubble role="user">
      {command ? <CommandTurn command={command} onOpen={onOpenCommand} /> : <p className={styles.text}>{text}</p>}
    </MessageBubble>
  );
}
