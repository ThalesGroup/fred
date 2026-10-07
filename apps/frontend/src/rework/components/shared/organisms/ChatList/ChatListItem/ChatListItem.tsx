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
import React, { useId } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import { Link, useLocation } from "react-router-dom";
import styles from "./ChatListItem.module.scss";

interface ChatListItemProps {
  sessionId: string;
  href: string;
  label: string;
  agentName?: string;
  agentDeleted?: boolean;
  dateLabel?: string;
  onDelete: (e: React.MouseEvent) => void;
}

export function ChatListItem({
  sessionId,
  href,
  label,
  agentName,
  agentDeleted,
  dateLabel,
  onDelete,
}: ChatListItemProps) {
  const { t } = useTranslation();
  const statusId = useId();
  const deletedStatus = t("chatbot.deletedAgentTooltip");
  const location = useLocation();
  const isSelected = location.search.includes(`session=${sessionId}`);

  const item = (
    <Link
      to={href}
      className={styles.chatItemContainer}
      data-selected={isSelected}
      aria-describedby={agentDeleted ? statusId : undefined}
    >
      <div className={styles.chatDescription}>
        <div className={styles.title}>{label}</div>
        {/* Only the agent name shrinks so the date stays readable. */}
        {(agentName || dateLabel) && (
          <div className={styles.meta}>
            {agentName && (
              <span
                className={styles.agentName}
                data-agent-deleted={agentDeleted}
                title={agentDeleted ? undefined : agentName}
              >
                {agentName}
              </span>
            )}
            {agentName && dateLabel && <span className={styles.metaSeparator}>·</span>}
            {dateLabel && <span className={styles.dateLabel}>{dateLabel}</span>}
          </div>
        )}
      </div>
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
  return agentDeleted ? <Tooltip text={deletedStatus}>{item}</Tooltip> : item;
}
