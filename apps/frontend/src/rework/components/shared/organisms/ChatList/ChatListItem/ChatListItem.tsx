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
import React from "react";
import { Link, useLocation } from "react-router-dom";
import styles from "./ChatListItem.module.scss";

interface ChatListItemProps {
  sessionId: string;
  href: string;
  label: string;
  agentName?: string;
  dateLabel?: string;
  onDelete: (e: React.MouseEvent) => void;
}

export function ChatListItem({ sessionId, href, label, agentName, dateLabel, onDelete }: ChatListItemProps) {
  const location = useLocation();
  const isSelected = location.search.includes(`session=${sessionId}`);

  return (
    <Link to={href} className={styles.chatItemContainer} data-selected={isSelected}>
      <div className={styles.chatDescription}>
        <div className={styles.title}>{label}</div>
        {/* Meta line: the date is the fixed part and must stay whole ("18/08/26
            - 09:42" split over two lines was unreadable), so only the agent
            name gives way — it shrinks and ellipsizes, with the full name on
            hover. */}
        {(agentName || dateLabel) && (
          <div className={styles.meta}>
            {agentName && (
              <span className={styles.agentName} title={agentName}>
                {agentName}
              </span>
            )}
            {agentName && dateLabel && <span className={styles.metaSeparator}>·</span>}
            {dateLabel && <span className={styles.dateLabel}>{dateLabel}</span>}
          </div>
        )}
      </div>
      <span className={styles.chatActions}>
        <DeleteIconButton size="small" onClick={onDelete} />
      </span>
    </Link>
  );
}
