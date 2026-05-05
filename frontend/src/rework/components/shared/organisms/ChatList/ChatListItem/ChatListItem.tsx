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

import styles from "./ChatListItem.module.scss";
import {
  SessionWithFiles,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
} from "../../../../../../slices/agentic/agenticOpenApi.ts";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { useToast } from "../../../../../../components/ToastProvider.tsx";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import React from "react";

interface ChatListItemProps {
  chat: SessionWithFiles;
  onDelete: () => void;
}

export default function ChatListItem({ chat, onDelete }: ChatListItemProps) {
  const [deleteSessionMutation] = useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation();

  const { showError } = useToast();
  const location = useLocation();
  const navigate = useNavigate();
  const { t } = useTranslation();

  const isSelected = location.pathname.endsWith(`/chat/${chat.id}`);

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    try {
      await deleteSessionMutation({ sessionId: chat.id }).unwrap();
      onDelete();

      if (isSelected) {
        navigate(`/team/${chat.team_id}/agents`);
      }
    } catch (error) {
      console.error("Failed to delete conversation: ", error);
      showError(t("sidebar.deleteSessionFailed"));
    }
  };

  return (
    <Link to={`team/${chat.team_id}/chat/${chat.id}`}>
      <div className={styles.chatItemContainer} title={chat.title} data-selected={isSelected}>
        <div className={styles.chatDescription}>
          <div className={styles.title}>{chat.title}</div>
          <div className={styles.metadata}>
            <span className={styles.agent}>
              <div className={styles.agentName}>{chat.agents.length !== 0 ? chat.agents[0].name : ""}</div>
            </span>
            <span className={styles.separator}>•</span>
            <span className={styles.date}>{new Intl.DateTimeFormat().format(new Date(chat.updated_at))}</span>
          </div>
        </div>
        <span className={styles.chatActions}>
          <IconButton
            color={"error"}
            variant={"icon"}
            size={"medium"}
            icon={{ category: "outlined", type: "delete_forever", filled: true }}
            onClick={handleDelete}
          />
        </span>
      </div>
    </Link>
  );
}
