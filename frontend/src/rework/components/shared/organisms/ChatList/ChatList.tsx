import styles from "./ChatList.module.scss";
import { useTranslation } from "react-i18next";

interface ChatListProps {
  teamId: string;
}

/**
 * Render the sidebar conversation area without calling legacy session APIs.
 *
 * Why this component exists:
 * - the personal-team baseline should no longer depend on `agentic-backend`
 *   session endpoints before the managed session metadata slice is ready
 *
 * How to use it:
 * - mount it in team sidebars during the bootstrap and managed-agent migration
 *
 * Example:
 * - `<ChatList teamId="personal" />`
 */
export default function ChatList({ teamId }: ChatListProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.chatListContainer} data-team-id={teamId}>
      <div className={styles.chatListHeader}>{t("rework.sidebar.chatList.title")}</div>
      <div className={styles.chatListItems}>
        <div className={styles.chatListPlaceholder}>{t("rework.sidebar.chatList.emptyManaged")}</div>
      </div>
    </div>
  );
}
