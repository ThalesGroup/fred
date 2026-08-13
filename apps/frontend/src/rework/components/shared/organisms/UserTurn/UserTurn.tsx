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

import { memo, useCallback, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { UserMessage } from "@shared/molecules/UserMessage/UserMessage";
import { ActionBar } from "@shared/molecules/ActionBar/ActionBar";
import type { Action } from "@shared/molecules/ActionBar/ActionBar";
import styles from "./UserTurn.module.css";

interface UserTurnProps {
  text: string;
  /** Called when user clicks the edit action. If omitted, edit action is hidden. */
  onEdit?: (text: string) => void;
}

// Memoized alongside AssistantTurn — see #2221.
export const UserTurn = memo(function UserTurn({ text, onEdit }: UserTurnProps) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  const copyAction = useCallback(() => {
    // User messages are plain text — none of the assistant turn's email-safe
    // HTML serialisation applies here, so writeText is the whole job.
    // A failed copy stays silent on purpose: the icon simply not flipping IS
    // the feedback, and the clipboard API only fails in degraded contexts
    // (missing permission, non-secure origin) that a toast would not fix.
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      })
      .catch(() => {});
  }, [text]);

  // Same confirmation as AssistantTurn (#2336): the button itself is the
  // receipt — content_copy → check for 2s, no toast, no colour change.
  const actions: Action[] = useMemo(() => {
    const list: Action[] = [];
    if (onEdit) {
      list.push({
        id: "edit",
        icon: "edit",
        label: t("chatbot.editMessage"),
        onClick: () => onEdit(text),
      });
    }
    list.push({
      id: "copy",
      icon: copied ? "check" : "content_copy",
      label: copied ? t("chatbot.copyMessage.copied") : t("chatbot.copyMessage.tooltip"),
      onClick: copyAction,
    });
    return list;
  }, [onEdit, text, copied, copyAction, t]);

  return (
    <div className={styles.turn}>
      {/* Beside the bubble (user turns are right-aligned), revealed on hover. */}
      <ActionBar actions={actions} className={styles.actions} />
      <UserMessage text={text} />
    </div>
  );
});
