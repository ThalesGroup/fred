import ChatListItem from "@shared/organisms/ChatList/ChatListItem/ChatListItem.tsx";
import styles from "./ChatList.module.scss";
import { useTranslation } from "react-i18next";
import { useGetSessionsAgenticV1ChatbotSessionsGetQuery } from "../../../../../slices/agentic/agenticOpenApi.ts";

interface ChatListProps {
  teamId: string;
}

export default function ChatList({ teamId }: ChatListProps) {
  const { data: sessions, refetch: refetchSessions } = useGetSessionsAgenticV1ChatbotSessionsGetQuery(
    { teamId },
    {
      refetchOnMountOrArgChange: true,
      refetchOnFocus: true,
      refetchOnReconnect: true,
    },
  );
  const sortedSessions = sessions?.slice().sort((a, b) => {
    const dateA = new Date(a.updated_at).getTime();
    const dateB = new Date(b.updated_at).getTime();
    return dateB - dateA;
  });
  const { t } = useTranslation();

  return (
    <div className={styles["chat-list-container"]}>
      <div className={styles["chat-list-header"]}>{t("rework.sidebar.chatList.title")}</div>
      <div className={styles["chat-list-items"]}>
        {sortedSessions?.map((session) => <ChatListItem key={session.id} chat={session} onDelete={refetchSessions} />)}
      </div>
    </div>
  );
}
