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
  dateLabel?: string;
  onDelete: (e: React.MouseEvent) => void;
}

export function ChatListItem({ sessionId, href, label, dateLabel, onDelete }: ChatListItemProps) {
  const location = useLocation();
  const isSelected = location.search.includes(`session=${sessionId}`);

  return (
    <Link to={href} className={styles.chatItemContainer} data-selected={isSelected}>
      <div className={styles.chatDescription}>
        <div className={styles.title}>{label}</div>
        {dateLabel && <div className={styles.date}>{dateLabel}</div>}
      </div>
      <span className={styles.chatActions}>
        <DeleteIconButton size="small" onClick={onDelete} />
      </span>
    </Link>
  );
}
