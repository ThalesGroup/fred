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

import React from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation,
  useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { ChatListItem } from "./ChatListItem/ChatListItem.tsx";
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

export default function ChatList({ teamId }: ChatListProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const { data: sessions, isLoading } = useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery(
    { teamId: teamId! },
    { skip: !teamId, pollingInterval: 30_000 },
  );

  const [deleteSession] = useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation();

  const isEmpty = !isLoading && (!sessions || sessions.length === 0);

  const handleDelete = (sessionId: string, href: string) => async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    await deleteSession({ teamId: teamId!, sessionId })
      .unwrap()
      .catch(() => {});
    const sessionPath = href.split("?")[0];
    if (window.location.pathname === sessionPath) {
      navigate(`/team/${teamId}/agents`);
    }
  };

  return (
    <div className={styles.chatListContainer} data-team-id={teamId}>
      <div className={styles.chatListHeader}>{t("rework.sidebar.chatList.title")}</div>
      <div className={styles.chatListItems}>
        {isLoading && <div className={styles.chatListPlaceholder}>{t("rework.sidebar.chatList.loading")}</div>}
        {isEmpty && <div className={styles.chatListPlaceholder}>{t("rework.sidebar.chatList.emptyManaged")}</div>}
        {sessions?.map((session) => {
          if (!session.agent_instance_id) return null;
          const href = `/team/${teamId}/managed-chat/${session.agent_instance_id}?session=${session.session_id}`;
          return (
            <ChatListItem
              key={session.session_id}
              sessionId={session.session_id}
              href={href}
              label={session.title || session.session_id.slice(0, 8) + "…"}
              dateLabel={formatRelativeDate(session.updated_at)}
              onDelete={handleDelete(session.session_id, href)}
            />
          );
        })}
      </div>
    </div>
  );
}
