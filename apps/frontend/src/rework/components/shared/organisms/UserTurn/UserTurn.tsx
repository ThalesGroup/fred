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

import { memo } from "react";
import { useTranslation } from "react-i18next";
import { UserMessage } from "@shared/molecules/UserMessage/UserMessage";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { useCopyToClipboard } from "@hooks/useCopyToClipboard";
import styles from "./UserTurn.module.css";

interface UserTurnProps {
  text: string;
  /** Called when user clicks the edit action. If omitted, edit action is hidden. */
  onEdit?: (text: string) => void;
}

// Memoized alongside AssistantTurn — see #2221.
export const UserTurn = memo(function UserTurn({ text, onEdit }: UserTurnProps) {
  const { t } = useTranslation();
  // The button itself confirms the copy (content_copy → green check) — no toast.
  const { copied, copy } = useCopyToClipboard(text);

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
          <span className={copied ? styles.copyPop : undefined}>
            <IconButton
              variant="icon"
              size="small"
              color={copied ? "success" : undefined}
              icon={{ category: "outlined", type: copied ? "check" : "content_copy" }}
              aria-label={t("chatbot.copyMessage.tooltip")}
              onClick={copy}
            />
          </span>
        </Tooltip>
      </div>
      <UserMessage text={text} />
    </div>
  );
});
