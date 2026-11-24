// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useHref } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar";
import { isPersonalTeamId } from "@shared/utils/teamId";
import { conversationHref } from "@core/hooks/useBackgroundTurnNotifications";
import type { ConversationTraceDetail } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TRACE_TRANSLATION_PREFIX, TraceFact, TraceIdentifier, useTraceCopy } from "./traceControls";
import styles from "./ConversationTraces.module.css";

export function ConversationTraceOverview({ conversation }: { conversation: ConversationTraceDetail }) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const { copied, copyFailed, copy } = useTraceCopy();
  const agentId = conversation.agent_instance_id;
  const chatHref = useHref(
    conversationHref(
      encodeURIComponent(conversation.team_id),
      encodeURIComponent(agentId ?? ""),
      encodeURIComponent(conversation.session_id),
    ),
  );
  const cutoff = conversation.consent_cutoff;
  const supportAccess = conversation.local_content_access
    ? t("localAccess")
    : cutoff
      ? t("sharedThrough", { number: cutoff.turn_number })
      : t("noneShared");
  const unavailable = t("unavailable");
  const userName = conversation.user_display_name || unavailable;
  const fields = [
    {
      nameLabel: t("conversationName"),
      name: conversation.title || t("maskedConversation"),
      idLabel: t("conversationId"),
      id: conversation.session_id,
    },
    {
      nameLabel: t("teamName"),
      name: isPersonalTeamId(conversation.team_id)
        ? i18n.t("rework.home.topTeams.personalSpace")
        : conversation.team_name,
      idLabel: t("teamId"),
      id: conversation.team_id,
    },
    {
      nameLabel: t("agentInstanceName"),
      name: conversation.agent_display_name,
      idLabel: t("agentInstanceId"),
      id: agentId,
      kind: conversation.agent_kind ?? null,
    },
    {
      nameLabel: t("userName"),
      name:
        conversation.user_display_name || conversation.user_avatar_image_url ? (
          <div className={styles.overviewUser}>
            <div aria-hidden="true">
              <UserAvatar name={userName} imageUrl={conversation.user_avatar_image_url} size="x-small" />
            </div>
            {userName}
          </div>
        ) : null,
      idLabel: t("userId"),
      id: conversation.user_id,
    },
  ];

  return (
    <section className={styles.overview} aria-labelledby="trace-overview-heading">
      <header className={styles.overviewHeader}>
        <div>
          <h2 id="trace-overview-heading">{t("conversationDetails")}</h2>
          <p>{supportAccess}</p>
        </div>
        {conversation.retained_after_delete ? (
          <Chip label={t("retainedAfterDelete")} />
        ) : agentId ? (
          <div className={styles.overviewCopy}>
            <Button
              type="button"
              size="small"
              color="secondary"
              variant="outlined"
              icon={{ category: "outlined", type: copied ? "check" : "content_copy" }}
              onClick={() => void copy(new URL(chatHref, window.location.origin).href)}
            >
              {t("copyChatLink")}
            </Button>
            <span role="status">{copied ? t("copied") : ""}</span>
            {copyFailed && <span role="alert">{t("copyFailed")}</span>}
          </div>
        ) : null}
      </header>
      <div className={styles.overviewGrid}>
        {fields.map(({ nameLabel, name, idLabel, id, kind }) => (
          <dl key={idLabel} className={styles.overviewGroup}>
            <TraceFact label={nameLabel}>{name || unavailable}</TraceFact>
            <TraceFact label={idLabel}>{id ? <TraceIdentifier label={idLabel} value={id} /> : unavailable}</TraceFact>
            {kind !== undefined && <TraceFact label={t("agentKind")}>{kind || unavailable}</TraceFact>}
          </dl>
        ))}
      </div>
    </section>
  );
}
