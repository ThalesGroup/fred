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

import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton.tsx";
import { ThinkingDots } from "@shared/atoms/ThinkingDots/ThinkingDots";
import { useSessionUnread, useTurnStatus } from "@core/hooks/backgroundTurns";
import React, { useId } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../../hooks/useFrontendProperties";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { Link, useLocation } from "react-router-dom";
import styles from "./ChatListItem.module.scss";

interface ChatListItemProps {
  sessionId: string;
  href: string;
  label: string;
  agentName?: string;
  agentTooltipName?: string;
  agentDeleted?: boolean;
  dateLabel?: string;
  onDelete: (e: React.MouseEvent) => void;
}

export function ChatListItem({
  sessionId,
  href,
  label,
  agentName,
  agentTooltipName,
  agentDeleted,
  dateLabel,
  onDelete,
}: ChatListItemProps) {
  const { t } = useTranslation();
  const { agentsNicknameSingular } = useFrontendProperties();
  const statusId = useId();
  const deletedStatus = t("chatbot.deletedAgentTooltip", { agentsNicknameSingular });
  const fullAgentName = agentTooltipName ?? agentName;
  const location = useLocation();
  const isSelected = location.search.includes(`session=${sessionId}`);
  const turnStatus = useTurnStatus(sessionId);
  const unread = useSessionUnread(sessionId);

  const item = (
    <Link
      to={href}
      className={styles.chatItemContainer}
      data-selected={isSelected}
      aria-describedby={agentDeleted ? statusId : undefined}
    >
      <div className={styles.chatDescription} data-read-only={agentDeleted}>
        <div className={styles.title} data-unread={unread}>
          {label}
          {unread && <span className={styles.accessibleStatus}>{t("rework.sidebar.chatList.unread")}</span>}
        </div>
        {/* Only the agent name shrinks so the date stays readable. */}
        {(agentName || dateLabel) && (
          <div className={styles.meta}>
            {agentName && (
              <span
                className={styles.agentLabel}
                data-agent-deleted={agentDeleted}
                title={agentDeleted ? undefined : agentName}
              >
                <span className={styles.agentName}>{agentName}</span>
                {agentDeleted && <span className={styles.deletedSuffix}> {t("chatbot.deletedAgentSuffix")}</span>}
              </span>
            )}
            {agentName && dateLabel && <span className={styles.metaSeparator}>·</span>}
            {dateLabel && <span className={styles.dateLabel}>{dateLabel}</span>}
          </div>
        )}
        {turnStatus === "awaiting_input" && !agentDeleted && (
          <span className={styles.awaitingInput}>{t("rework.sidebar.chatList.awaitingInput")}</span>
        )}
      </div>
      {turnStatus === "running" && (
        <span className={styles.turnStatus}>
          <ThinkingDots size="small" />
          <span className={styles.accessibleStatus}>{t("rework.sidebar.chatList.answering")}</span>
        </span>
      )}
      {unread && turnStatus === null && (
        <span className={styles.turnStatus} title={t("rework.sidebar.chatList.answerReady")} aria-hidden="true">
          <span className={styles.unreadDot} />
        </span>
      )}
      {agentDeleted && (
        <span id={statusId} className={styles.accessibleStatus}>
          {deletedStatus}
        </span>
      )}
      <span className={styles.chatActions}>
        <DeleteIconButton size="small" onClick={onDelete} />
      </span>
    </Link>
  );
  return agentDeleted ? (
    <Tooltip text={fullAgentName ? `${fullAgentName} - ${deletedStatus}` : deletedStatus}>{item}</Tooltip>
  ) : (
    item
  );
}
