import { useGetSessionsAgenticV1ChatbotSessionsGetQuery } from "../../../../../slices/agentic/agenticOpenApi.ts";
import ChatListItem from "@shared/organisms/ChatList/ChatListItem/ChatListItem.tsx";
import styles from "./ChatList.module.scss";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon.tsx";

export default function ChatList() {
  const { data: sessions, refetch: refetchSessions } = useGetSessionsAgenticV1ChatbotSessionsGetQuery(undefined, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
    refetchOnReconnect: true,
  });
  const sortedSessions = sessions?.slice().sort((a, b) => {
    const dateA = new Date(a.updated_at).getTime();
    const dateB = new Date(b.updated_at).getTime();
    return dateB - dateA;
  });
  const { t } = useTranslation();

  const maxChat = 1;

  return (
    <div className={styles["chat-list-container"]}>
      <div className={styles["chat-list-header"]}>
        {t("rework.sidebar.chatList.title")}
        <div
          className={`${styles["chat-list-header-counter"]} ${sessions?.length >= maxChat ? styles["overflow"] : ""}`}
          onClick={() => refetchSessions()}
        >
          <span className={styles["overflow-icon"]}>
            <Icon category={"outlined"} type={"Info"} />
          </span>
          {sessions?.length}/{maxChat}
        </div>
      </div>
      <div className={styles["chat-list-items"]}>
        {sortedSessions?.map((session) => (
          <ChatListItem key={session.id} chat={session} refetchSessions={refetchSessions} />
        ))}
       </div>
    </div>
  );
}
