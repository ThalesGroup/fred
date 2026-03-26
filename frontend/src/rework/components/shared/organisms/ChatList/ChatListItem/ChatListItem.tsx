import styles from "./ChatListItem.module.scss";
import {
  SessionWithFiles,
  useDeleteSessionAgenticV1ChatbotSessionSessionIdDeleteMutation,
} from "../../../../../../slices/agentic/agenticOpenApi.ts";
import Icon from "@shared/atoms/Icon/Icon.tsx";
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

  const isSelected = location.pathname === `/chat/${chat.id}`;

  const handleDelete = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();

    try {
      await deleteSessionMutation({ sessionId: chat.id }).unwrap();
      onDelete();

      if (isSelected) {
        navigate("/");
      }
    } catch (error) {
      console.error("Failed to delete conversation: ", error);
      showError(t("sidebar.deleteSessionFailed"));
    }
  };

  return (
    <Link to={`/chat/${chat.id}`}>
      <div className={styles["chat-item-container"]} title={chat.title}>
        <div className={styles["chat-description"]}>
          <div className={styles["title"]}>{chat.title}</div>
          <div className={styles["metadata"]}>
            <span className={styles["agent"]}>
              <span className={styles["icon"]}>
                <Icon category={"outlined"} type={"Person"} />
              </span>
              <div className={styles["agent-name"]}>{chat.agents.length !== 0 ? chat.agents[0].name : ""}</div>
            </span>
            <span className={styles["separator"]}>•</span>
            <span className={styles["date"]}>{new Intl.DateTimeFormat().format(new Date(chat.updated_at))}</span>
          </div>
        </div>
        <span className={styles["chat-actions"]}>
          <IconButton
            color={"error"}
            variant={"icon"}
            size={"medium"}
            icon={{ category: "outlined", type: "Delete", filled: true }}
            onClick={handleDelete}
          />
        </span>
      </div>
    </Link>
  );
}
