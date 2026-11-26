// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import type { ConversationTraceDetail } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TRACE_TRANSLATION_PREFIX, TraceIdentifier } from "./traceControls";
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

export function ConversationTraceOverview({ conversation }: { conversation: ConversationTraceDetail }) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const cutoff = conversation.consent_cutoff;
  const supportAccess = conversation.local_content_access
    ? t("localAccess")
    : cutoff
      ? t("sharedThrough", { number: cutoff.turn_number })
      : t("noneShared");

  return (
    <section className={styles.overview} aria-labelledby="trace-overview-heading">
      <header className={styles.overviewHeader}>
        <div className={styles.overviewConversation}>
          <h2 id="trace-overview-heading">
            <OverviewText value={conversation.title || t("maskedConversation")} />
          </h2>
          <div className={styles.overviewConversationMeta}>
            <TraceIdentifier label={t("conversationId")} value={conversation.session_id} truncate />
            <span className={styles.overviewAccess} title={supportAccess}>
              {supportAccess}
            </span>
          </div>
        </div>
      </header>
      <div className={styles.overviewGrid}>
        <div className={styles.overviewGroup}>
          <h3>{t("overviewTeam")}</h3>
          <TraceIdentifier label={t("teamId")} value={conversation.team_id} truncate />
        </div>
        <div className={styles.overviewGroup}>
          <h3>{t("overviewAgent")}</h3>
          <strong>
            <OverviewText value={conversation.agent_display_name || t("unavailable")} />
          </strong>
        </div>
      </div>
    </section>
  );
}
