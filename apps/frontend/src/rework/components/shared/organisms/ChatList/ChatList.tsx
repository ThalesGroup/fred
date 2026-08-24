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

import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation,
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { ChatListItem } from "./ChatListItem/ChatListItem.tsx";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import styles from "./ChatList.module.scss";

type Session = NonNullable<
  ReturnType<typeof useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery>["data"]
>[number];

interface ChatListProps {
  teamId?: string;
}

// "12/03/26 - 13:03" — fixed DD/MM/YY - HH:mm, not locale-dependent
// (unlike `toLocaleDateString()`, which flips day/month order in en-US).
function formatSessionDate(dateStr: string | undefined): string {
  if (!dateStr) return "";
  const date = new Date(dateStr);
  const day = String(date.getDate()).padStart(2, "0");
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const year = String(date.getFullYear()).slice(-2);
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${day}/${month}/${year} - ${hours}:${minutes}`;
}

export default function ChatList({ teamId }: ChatListProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { showConfirmationDialog } = useConfirmationDialog();
  const [groupByAgent, setGroupByAgent] = useState(false);

  const { data: sessions, isLoading } = useGetTeamSessionsControlPlaneV1TeamsTeamIdSessionsGetQuery(
    { teamId: teamId! },
    { skip: !teamId, pollingInterval: 30_000 },
  );
  const { data: agentInstances } = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId: teamId! },
    { skip: !teamId },
  );
  const agentNameByInstanceId = new Map(
    agentInstances?.map((instance) => [instance.agent_instance_id, instance.display_name]),
  );

  const [deleteSession] = useDeleteTeamSessionControlPlaneV1TeamsTeamIdSessionsSessionIdDeleteMutation();

  const managedSessions = (sessions ?? []).filter((session): session is Session & { agent_instance_id: string } =>
    Boolean(session.agent_instance_id),
  );
  const isEmpty = !isLoading && managedSessions.length === 0;

  const handleDelete = (sessionId: string, href: string, label: string) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    showConfirmationDialog({
      criticalAction: true,
      title: t("rework.sidebar.chatList.deleteDialog.title"),
      message: t("rework.sidebar.chatList.deleteDialog.message", { name: label }),
      confirmButtonLabel: t("rework.sidebar.chatList.deleteDialog.confirm"),
      cancelButtonLabel: t("rework.sidebar.chatList.deleteDialog.cancel"),
      onConfirm: async () => {
        await deleteSession({ teamId: teamId!, sessionId })
          .unwrap()
          .catch(() => {});
        const sessionPath = href.split("?")[0];
        if (window.location.pathname === sessionPath) {
          navigate(`/team/${teamId}/agents`);
        }
      },
    });
  };

  const renderItem = (session: Session & { agent_instance_id: string }, showAgentName: boolean) => {
    const href = `/team/${teamId}/managed-chat/${session.agent_instance_id}?session=${session.session_id}`;
    const label = session.title || session.session_id.slice(0, 8) + "…";
    return (
      <ChatListItem
        key={session.session_id}
        sessionId={session.session_id}
        href={href}
        label={label}
        agentName={showAgentName ? agentNameByInstanceId.get(session.agent_instance_id) : undefined}
        dateLabel={formatSessionDate(session.updated_at)}
        onDelete={handleDelete(session.session_id, href, label)}
      />
    );
  };

  const groups = groupByAgent
    ? Array.from(
        managedSessions
          .reduce((byAgent, session) => {
            const agentName =
              agentNameByInstanceId.get(session.agent_instance_id) ?? t("rework.sidebar.chatList.unknownAgent");
            (byAgent.get(agentName) ?? byAgent.set(agentName, []).get(agentName)!).push(session);
            return byAgent;
          }, new Map<string, (Session & { agent_instance_id: string })[]>())
          .entries(),
      ).sort(([a], [b]) => a.localeCompare(b, undefined, { sensitivity: "base" }))
    : null;

  return (
    <div className={styles.chatListContainer} data-team-id={teamId}>
      <div className={styles.chatListHeader}>
        {t("rework.sidebar.chatList.title")}
        <Tooltip text={t("rework.sidebar.chatList.groupByAgent")}>
          <IconButton
            color={groupByAgent ? "primary" : "on-surface-retreat"}
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "category", filled: groupByAgent }}
            aria-pressed={groupByAgent}
            aria-label={t("rework.sidebar.chatList.groupByAgent")}
            onClick={() => setGroupByAgent((value) => !value)}
          />
        </Tooltip>
      </div>
      <div className={styles.chatListItems}>
        {isLoading && <div className={styles.chatListPlaceholder}>{t("rework.sidebar.chatList.loading")}</div>}
        {isEmpty && <div className={styles.chatListPlaceholder}>{t("rework.sidebar.chatList.emptyManaged")}</div>}
        {groups
          ? groups.map(([agentName, groupSessions]) => (
              <div key={agentName}>
                <div className={styles.groupHeader} title={agentName}>
                  {agentName}
                </div>
                {groupSessions.map((session) => renderItem(session, false))}
              </div>
            ))
          : managedSessions.map((session) => renderItem(session, true))}
      </div>
    </div>
  );
}
