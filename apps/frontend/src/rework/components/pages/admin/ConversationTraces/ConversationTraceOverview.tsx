// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { useHref } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
import Icon from "@shared/atoms/Icon/Icon";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar";
import { resolveAgentIcon } from "@shared/utils/agentIcon";
import { isPersonalTeamId } from "@shared/utils/teamId";
import { conversationHref } from "@core/hooks/useBackgroundTurnNotifications";
import { useFrontendProperties } from "src/hooks/useFrontendProperties";
import type { ConversationTraceDetail } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TRACE_TRANSLATION_PREFIX, TraceIdentifier, useTraceCopy } from "./traceControls";
import styles from "./ConversationTraces.module.css";

function TraceIdentity({
  label,
  name,
  avatar,
  idLabel,
  id,
  children,
}: {
  label: string;
  name: string;
  avatar: ReactNode;
  idLabel: string;
  id?: string | null;
  children?: ReactNode;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  return (
    <div className={styles.overviewGroup}>
      <h3>{label}</h3>
      <div className={styles.overviewIdentity}>
        <div className={styles.overviewAvatar} aria-hidden="true">
          {avatar}
        </div>
        <div className={styles.overviewIdentityBody}>
          <strong>{name}</strong>
          {children}
          {id ? <TraceIdentifier label={idLabel} value={id} /> : <small>{t("unavailable")}</small>}
        </div>
      </div>
    </div>
  );
}

export function ConversationTraceOverview({ conversation }: { conversation: ConversationTraceDetail }) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const { agentIconName, defaultPersonalAvatarFile, defaultTeamAvatarFile } = useFrontendProperties();
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
  const isPersonal = isPersonalTeamId(conversation.team_id);
  const teamName = isPersonal ? i18n.t("rework.home.topTeams.personalSpace") : conversation.team_name || unavailable;
  const defaultTeamPicture = isPersonal ? defaultPersonalAvatarFile : defaultTeamAvatarFile;
  const teamPicture =
    conversation.team_avatar_image_url || (defaultTeamPicture ? `/images/${defaultTeamPicture}` : null);
  const agentName = conversation.agent_display_name || unavailable;
  const role = conversation.agent_role?.trim();
  const description = conversation.agent_description?.trim();
  const icon = resolveAgentIcon(
    { display_name: conversation.agent_display_name, role: role || "", description },
    agentIconName,
  );

  return (
    <section className={styles.overview} aria-labelledby="trace-overview-heading">
      <header className={styles.overviewHeader}>
        <div className={styles.overviewConversation}>
          <h2 id="trace-overview-heading">{conversation.title || t("maskedConversation")}</h2>
          <div className={styles.overviewConversationMeta}>
            <TraceIdentifier label={t("conversationId")} value={conversation.session_id} />
            <span className={styles.overviewAccess}>{supportAccess}</span>
          </div>
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
            <span role="status" className={styles.overviewCopyStatus}>
              {copied ? t("copied") : ""}
            </span>
            {copyFailed && <span role="alert">{t("copyFailed")}</span>}
          </div>
        ) : null}
      </header>
      <div className={styles.overviewGrid}>
        <TraceIdentity
          label={t("overviewUser")}
          name={conversation.user_display_name || unavailable}
          idLabel={t("userId")}
          id={conversation.user_id}
          avatar={
            <UserAvatar
              name={conversation.user_display_name || unavailable}
              imageUrl={conversation.user_avatar_image_url}
              size="small"
            />
          }
        />
        <TraceIdentity
          label={t("overviewTeam")}
          name={teamName}
          idLabel={t("teamId")}
          id={conversation.team_id}
          avatar={<UserAvatar name={teamName} imageUrl={teamPicture} size="small" />}
        />
        <TraceIdentity
          label={t("overviewAgent")}
          name={agentName}
          idLabel={t("agentInstanceId")}
          id={agentId}
          avatar={
            <span className={styles.overviewAgentIcon}>
              <Icon type={icon} />
            </span>
          }
        >
          {role && role !== agentName && <p>{role}</p>}
          {description && description !== role && description !== agentName && <p>{description}</p>}
          {conversation.agent_kind && (
            <p className={styles.overviewKind}>
              {t("agentKind")} <span>{conversation.agent_kind}</span>
            </p>
          )}
        </TraceIdentity>
      </div>
    </section>
  );
}
