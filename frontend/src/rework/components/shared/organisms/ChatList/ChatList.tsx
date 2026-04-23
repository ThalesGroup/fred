import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./ChatList.module.scss";

interface ChatListProps {
  teamId?: string;
}

function formatRelativeDate(dateStr: string | undefined): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

/**
 * Render the sidebar conversation list from control-plane session metadata.
 *
 * Why this component exists:
 * - replaces the intentional placeholder once control-plane session metadata
 *   endpoints exist (Phase 5D)
 *
 * How to use it:
 * - mount it in team sidebars under `/team/:teamId/...`
 *
 * Example:
 * - `<ChatList teamId="personal" />`
 */
export default function ChatList({ teamId }: ChatListProps) {
  const { t } = useTranslation();

  const { data: sessions, isLoading } = useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery(
    { teamId: teamId! },
    { skip: !teamId, pollingInterval: 30_000 },
  );

  const isEmpty = !isLoading && (!sessions || sessions.length === 0);

  return (
    <div className={styles.chatListContainer} data-team-id={teamId}>
      <div className={styles.chatListHeader}>{t("rework.sidebar.chatList.title")}</div>
      <div className={styles.chatListItems}>
        {isLoading && (
          <div className={styles.chatListPlaceholder}>
            {t("rework.sidebar.chatList.loading")}
          </div>
        )}
        {isEmpty && (
          <div className={styles.chatListPlaceholder}>
            {t("rework.sidebar.chatList.emptyManaged")}
          </div>
        )}
        {sessions?.map((session) => {
          const href = session.agent_instance_id
            ? `/team/${teamId}/managed-chat/${session.agent_instance_id}?session=${session.session_id}`
            : undefined;

          const label = session.title || session.session_id.slice(0, 8) + "…";
          const dateLabel = formatRelativeDate(session.updated_at);

          if (!href) return null;

          return (
            <Link key={session.session_id} to={href} className={styles.chatListItem}>
              <span className={styles.chatListItemLabel}>{label}</span>
              {dateLabel && <span className={styles.chatListItemDate}>{dateLabel}</span>}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
