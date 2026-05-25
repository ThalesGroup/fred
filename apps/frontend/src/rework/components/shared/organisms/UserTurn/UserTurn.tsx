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

import { UserMessage } from "@shared/molecules/UserMessage/UserMessage";
import { ActionBar } from "@shared/molecules/ActionBar/ActionBar";
import type { Action } from "@shared/molecules/ActionBar/ActionBar";
import styles from "./UserTurn.module.css";

interface UserTurnProps {
  text: string;
  /** Called when user clicks the edit action. If omitted, edit action is hidden. */
  onEdit?: (text: string) => void;
}

export function UserTurn({ text, onEdit }: UserTurnProps) {
  const actions: Action[] = [
    {
      id: "copy",
      icon: "content_copy",
      label: "Copy message",
      onClick: () => { navigator.clipboard.writeText(text).catch(() => {}); },
    },
    ...(onEdit ? [{
      id: "edit",
      icon: "edit",
      label: "Edit message",
      onClick: () => onEdit(text),
    }] : []),
  ];

  return (
    <div className={styles.turn}>
      <UserMessage text={text} />
      <ActionBar actions={actions} className={styles.actions} />
    </div>
  );
}
