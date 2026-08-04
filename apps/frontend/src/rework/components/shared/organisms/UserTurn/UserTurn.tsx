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

import { memo, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { UserMessage } from "@shared/molecules/UserMessage/UserMessage";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import styles from "./UserTurn.module.css";

interface UserTurnProps {
  text: string;
  /** Called when user clicks the edit action. If omitted, edit action is hidden. */
  onEdit?: (text: string) => void;
}

// Memoized alongside AssistantTurn — see #2221.
export const UserTurn = memo(function UserTurn({ text, onEdit }: UserTurnProps) {
  const { t } = useTranslation();
  const { showSuccess } = useToast();

  const handleCopy = useCallback(() => {
    navigator.clipboard
      .writeText(text)
      // Short-lived confirmation — a copy is a trivial, self-evident action,
      // so the toast just blinks the success and clears fast.
      .then(() => showSuccess({ summary: t("chatbot.copyMessage.success"), duration: 2000 }))
      .catch(() => {});
  }, [text, showSuccess, t]);

  return (
    <div className={styles.turn}>
      {/* Beside the bubble (user turns are right-aligned), revealed on hover. */}
      <div className={styles.actions}>
        {onEdit && (
          <Tooltip text={t("chatbot.editMessage")}>
            <IconButton
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "edit" }}
              aria-label={t("chatbot.editMessage")}
              onClick={() => onEdit(text)}
            />
          </Tooltip>
        )}
        <Tooltip text={t("chatbot.copyMessage.tooltip")}>
          <IconButton
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "content_copy" }}
            aria-label={t("chatbot.copyMessage.tooltip")}
            onClick={handleCopy}
          />
        </Tooltip>
      </div>
      <UserMessage text={text} />
    </div>
  );
});
