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
import { writeRichClipboard } from "@rework/utils/clipboardUtils";
import { useCopyConfirmation } from "@hooks/useCopyConfirmation";
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
  const { copied, confirmCopied } = useCopyConfirmation();

  const copyAction = useCallback(() => {
    // Same call AssistantTurn makes when it has no rendered node to serialise:
    // with no HTML, writeRichClipboard writes text/plain only — which is all a
    // user message ever is. It also absorbs both clipboard failure modes (a
    // denied permission rejects; a non-secure origin has no navigator.clipboard
    // at all, so the property access throws synchronously).
    writeRichClipboard("", text).then((success) => {
      if (success) confirmCopied();
    });
  }, [text, confirmCopied]);

  const actions: Action[] = useMemo(
    () => [
      ...(onEdit ? [{ id: "edit", icon: "edit", label: t("chatbot.editMessage"), onClick: () => onEdit(text) }] : []),
      {
        id: "copy",
        icon: copied ? "check" : "content_copy",
        label: copied ? t("chatbot.copyMessage.copied") : t("chatbot.copyMessage.tooltip"),
        onClick: copyAction,
      },
    ],
    [onEdit, text, copied, copyAction, t],
  );

  return (
    <div className={styles.turn}>
      {/* Beside the bubble (user turns are right-aligned), revealed on hover. */}
      <ActionBar actions={actions} className={styles.actions} />
      <UserMessage text={text} />
    </div>
  );
});
