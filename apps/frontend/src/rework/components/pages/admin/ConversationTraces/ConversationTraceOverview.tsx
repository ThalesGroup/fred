// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
import Icon from "@shared/atoms/Icon/Icon";
import TextInput from "@shared/atoms/TextInput/TextInput";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import UserAvatar from "@shared/atoms/UserAvatar/UserAvatar";
import { resolveAgentIcon } from "@shared/utils/agentIcon";
import { isPersonalTeamId } from "@shared/utils/teamId";
import { useFrontendProperties } from "src/hooks/useFrontendProperties";
import type { ConversationTraceDetail } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TRACE_TRANSLATION_PREFIX, TraceIdentifier, useTraceChatHref, useTraceCopy } from "./traceControls";
import styles from "./ConversationTraces.module.css";

function OverviewText({ value }: { value: string }) {
  return (
    <Tooltip content={value} fill interactive>
      <span className={styles.overviewEllipsis} tabIndex={0}>
        {value}
      </span>
    </Tooltip>
  );
}

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
          <strong>
            <OverviewText value={name} />
          </strong>
          {children}
          {id ? <TraceIdentifier label={idLabel} value={id} truncate /> : <small>{t("unavailable")}</small>}
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
  const chatHref = useTraceChatHref(conversation);
  const chatUrl = () => new URL(chatHref, window.location.origin).href;
  const cutoff = conversation.consent_cutoff;
  const supportAccess = conversation.local_content_access
    ? t("localAccess")
    : cutoff
      ? t("sharedThrough", { number: cutoff.turn_number })
      : t("noneShared");
  const unavailable = t("unavailable");
  const title = conversation.title || t("maskedConversation");
  const email = conversation.user_email?.trim();
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
          <h2 id="trace-overview-heading">
            <OverviewText value={title} />
          </h2>
          <div className={styles.overviewConversationMeta}>
            <TraceIdentifier label={t("conversationId")} value={conversation.session_id} truncate />
            <span className={styles.overviewAccess} title={supportAccess}>
              {supportAccess}
            </span>
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
              onClick={() => void copy(chatUrl())}
            >
              {t("copyChatLink")}
            </Button>
            <span role="status" className={styles.overviewCopyStatus}>
              {copied ? t("copied") : ""}
            </span>
          </div>
        ) : null}
      </header>
      {copyFailed && agentId && !conversation.retained_after_delete && (
        <div className={styles.overviewCopyFallback}>
          <p role="alert">{t("chatLinkCopyFailed")}</p>
          <TextInput
            size="small"
            aria-label={t("chatLink")}
            readOnly
            value={chatUrl()}
            onFocus={(event) => event.currentTarget.select()}
          />
        </div>
      )}
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
        >
          {email && (
            <p>
              <OverviewText value={email} />
            </p>
          )}
        </TraceIdentity>
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
          {role && role !== agentName && (
            <p>
              <OverviewText value={role} />
            </p>
          )}
          {description && description !== role && description !== agentName && (
            <p>
              <OverviewText value={description} />
            </p>
          )}
          {conversation.agent_kind && (
            <p className={styles.overviewKind}>
              <OverviewText value={t("overviewKind", { kind: conversation.agent_kind })} />
            </p>
          )}
        </TraceIdentity>
      </div>
    </section>
  );
}
