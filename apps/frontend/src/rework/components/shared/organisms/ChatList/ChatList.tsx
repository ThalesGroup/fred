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

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../../../../../hooks/useFrontendProperties";
import { useListSessionsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { SessionDetails as Session } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { ChatListItem } from "./ChatListItem/ChatListItem.tsx";
import styles from "./ChatList.module.scss";
import { crossSessionRefreshOptions, useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";

interface ChatListProps {
  teamId?: string;
  spaceId?: string;
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

export default function ChatList({ teamId, spaceId }: ChatListProps) {
  const { t } = useTranslation();
  const { agentsNicknameSingular } = useFrontendProperties();
  const [groupByAgent, setGroupByAgent] = useState(false);

  const {
    currentData,
    isFetching: isLoading,
    isError,
    refetch,
  } = useListSessionsQuery(
    { spaceId: spaceId ?? "" },
    { ...crossSessionRefreshOptions(!spaceId), refetchOnMountOrArgChange: true },
  );
  useRefetchOnWindowFocus(refetch, !spaceId);
  const managedSessions = !spaceId || isError ? [] : (currentData ?? []);
  const agentName = (session: Session) =>
    session.agent_display_name || t("rework.sidebar.chatList.unknownAgent", { agentsNicknameSingular });
  const agentDeleted = (id: string) =>
    managedSessions.some((session) => session.agent_instance_id === id && session.agent_deleted);
  const isEmpty = !isLoading && !isError && managedSessions.length === 0;

  const renderItem = (session: Session & { agent_instance_id: string }, showAgentName: boolean) => {
    const href = `/team/${teamId}/managed-chat/${session.agent_instance_id}?session=${session.session_id}`;
    const label = session.title || session.session_id.slice(0, 8) + "…";
    return (
      <ChatListItem
        key={session.session_id}
        sessionId={session.session_id}
        href={href}
        label={label}
        agentName={showAgentName ? agentName(session) : undefined}
        agentTooltipName={agentName(session)}
        agentDeleted={agentDeleted(session.agent_instance_id)}
        dateLabel={formatSessionDate(session.updated_at)}
        deleteUnavailableReason={t("rework.weaverAgents.notConnected")}
      />
    );
  };

  const groups = groupByAgent
    ? Array.from(
        managedSessions
          .reduce((byAgent, session) => {
            const id = session.agent_instance_id;
            (byAgent.get(id) ?? byAgent.set(id, []).get(id)!).push(session);
            return byAgent;
          }, new Map<string, (Session & { agent_instance_id: string })[]>())
          .entries(),
      ).sort(([, a], [, b]) => agentName(a[0]).localeCompare(agentName(b[0]), undefined, { sensitivity: "base" }))
    : null;

  return (
    <div className={styles.chatListContainer} data-team-id={teamId}>
      <div className={styles.chatListHeader}>
        {t("rework.sidebar.chatList.title")}
        <Tooltip text={t("rework.sidebar.chatList.groupByAgent", { agentsNicknameSingular })}>
          <IconButton
            color={groupByAgent ? "primary" : "on-surface-retreat"}
            variant="icon"
            size="small"
            icon={{ category: "outlined", type: "category", filled: groupByAgent }}
            aria-pressed={groupByAgent}
            aria-label={t("rework.sidebar.chatList.groupByAgent", { agentsNicknameSingular })}
            onClick={() => setGroupByAgent((value) => !value)}
          />
        </Tooltip>
      </div>
      <div className={styles.chatListItems}>
        {isLoading && <div className={styles.chatListPlaceholder}>{t("rework.sidebar.chatList.loading")}</div>}
        {isError && <div className={styles.chatListPlaceholder}>{t("chatbot.historyUnavailable")}</div>}
        {isEmpty && (
          <div className={styles.chatListPlaceholder}>
            {t("rework.sidebar.chatList.emptyManaged", { agentsNicknameSingular })}
          </div>
        )}
        {groups
          ? groups.map(([agentId, groupSessions]) => (
              <div key={agentId} className={styles.agentGroup}>
                <div
                  className={styles.groupHeader}
                  data-agent-deleted={agentDeleted(agentId)}
                  title={agentName(groupSessions[0])}
                >
                  <span className={styles.groupName}>{agentName(groupSessions[0])}</span>
                  {agentDeleted(agentId) && (
                    <span className={styles.deletedSuffix}> {t("chatbot.deletedAgentSuffix")}</span>
                  )}
                </div>
                {groupSessions.map((session) => renderItem(session, false))}
              </div>
            ))
          : managedSessions.map((session) => renderItem(session, true))}
      </div>
    </div>
  );
}
