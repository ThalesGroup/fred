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

import { useConversationTraceAccess } from "@core/hooks/useConversationTraceAccess";
import { useState } from "react";
import { skipToken } from "@reduxjs/toolkit/query";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Chip from "@shared/atoms/Chip/Chip";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ConversationTraceTurn,
  TraceHttpAttempt,
  TraceToolCall,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TraceHttpAttemptEvidence, TraceHttpAttemptSummary, TraceHttpStatus } from "./ConversationTraceHttp";
import TraceJson from "./TraceJson";
import {
  TRACE_TRANSLATION_PREFIX,
  TraceEvidenceTabs,
  TraceFact,
  TraceIdentifier,
  TraceMaskedEvidence,
  canReadTraceArtifact,
  traceElapsedFormatter,
} from "./traceControls";
import styles from "./ConversationTraces.module.css";

const prefix = TRACE_TRANSLATION_PREFIX + ".tool";

function Payload({ label, data }: { label: string; data: unknown }) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  return (
    <section className={styles.httpPayload} aria-label={label}>
      <h4>{label}</h4>
      {data == null ? <p>{t("unavailable")}</p> : <TraceJson code={JSON.stringify(data, null, 2)} label={label} />}
    </section>
  );
}

function ToolPayloads({
  sessionId,
  turn,
  tool,
  cutoffRank,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  tool: TraceToolCall;
  cutoffRank?: number;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const canRead = canReadTraceArtifact(turn, cutoffRank, tool.observed_through_rank);
  const { organizationId } = useConversationTraceAccess();
  const query = enhancedControlPlaneApi.useGetConversationTraceToolEvidenceQuery(
    canRead && tool.completeness !== "unavailable"
      ? { organizationId, sessionId, exchangeId: turn.exchange_id, ref: tool.ref }
      : skipToken,
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  if (!canRead) return <TraceMaskedEvidence message={t("masked")} />;
  if (tool.completeness === "unavailable" || query.isError) return <p>{t("unavailable")}</p>;
  const evidence = query.currentData;
  if (!evidence || query.isFetching) return <p role="status">{t("loading")}</p>;
  return (
    <div className={styles.httpContent}>
      {evidence.partial && <p>{t("partial")}</p>}
      <Payload label={t("input")} data={evidence.input} />
      <Payload label={t("output")} data={evidence.output} />
      <Payload label={t("modelResult")} data={evidence.model_result} />
    </div>
  );
}

function ToolHttp({
  sessionId,
  turn,
  attempts,
  cutoffRank,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  attempts: TraceHttpAttempt[];
  cutoffRank?: number;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX + ".http" });
  const [selected, setSelected] = useState<string>();
  const active = attempts.find((item) => item.ref === selected) ?? attempts[0];
  return (
    <div className={styles.httpContent}>
      {attempts.length > 1 && (
        <div className={styles.httpAttemptButtons}>
          {attempts.map((item) => (
            <Button
              key={item.ref}
              type="button"
              size="2xs"
              variant={item.ref === active.ref ? "filled" : "outlined"}
              color={item.ref === active.ref ? "primary" : "on-surface"}
              aria-pressed={item.ref === active.ref}
              onClick={() => setSelected(item.ref)}
            >
              {t("attempt", { number: item.attempt })}
              {" · "}
              {item.status ?? t("noStatus")}
            </Button>
          ))}
        </div>
      )}
      <TraceHttpAttemptSummary attempt={active} turn={turn} />
      <TraceHttpAttemptEvidence sessionId={sessionId} turn={turn} attempt={active} cutoffRank={cutoffRank} />
    </div>
  );
}

export function ConversationTraceTool({
  sessionId,
  turn,
  tool,
  cutoffRank,
  view,
  onView,
  onModelCall,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  tool: TraceToolCall;
  cutoffRank?: number;
  view: string | null;
  onView: (view: string) => void;
  onModelCall: (callId: string) => void;
}) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: prefix });
  const attempts = tool.http_attempts ?? [];
  const tab = view === "http" && attempts.length > 0 ? "http" : "tool";
  const firstStatus = attempts[0]?.status;
  return (
    <article className={styles.evidence} aria-label={t("title")}>
      <header className={styles.evidenceHeader}>
        <h2>{tool.tool_name ?? t("unnamed")}</h2>
        <div className={styles.chips}>
          <span
            className={styles.outcome}
            data-outcome={tool.outcome === "error" ? "tool_or_capability" : tool.outcome}
          >
            {t("outcomes." + tool.outcome)}
          </span>
          {attempts.length === 1 && <TraceHttpStatus status={firstStatus} />}
          <Chip label={traceElapsedFormatter(i18n.language)(tool.duration_ms)} />
        </div>
      </header>
      <dl className={styles.callSummary}>
        <TraceFact label={t("source")}>{t("sources." + tool.source)}</TraceFact>
        <TraceFact label={t("attempt")}>{tool.attempt}</TraceFact>
        <TraceFact label={t("completeness")}>{t("completenessValue." + tool.completeness)}</TraceFact>
        {tool.call_id && (
          <TraceFact label={t("callId")}>
            <TraceIdentifier label={t("callId")} value={tool.call_id} />
          </TraceFact>
        )}
        {turn.trace_id && (
          <TraceFact label={t("traceId")}>
            <TraceIdentifier label={t("traceId")} value={turn.trace_id} />
          </TraceFact>
        )}
      </dl>
      {!!tool.model_calls?.length && (
        <div className={styles.httpAttemptButtons}>
          {tool.model_calls.map(({ call_id, relation }) => (
            <Button
              key={relation + call_id}
              type="button"
              size="2xs"
              variant="text"
              color="primary"
              onClick={() => onModelCall(call_id)}
            >
              {t("modelLink." + relation, { id: call_id })}
            </Button>
          ))}
        </div>
      )}
      {attempts.length > 0 && (
        <TraceEvidenceTabs
          tabs={[
            { key: "tool", label: t("inputOutput") },
            { key: "http", label: t("http") },
          ]}
          label={t("tabs")}
          selected={tab}
          onSelect={onView}
        />
      )}
      {tab === "http" ? (
        <ToolHttp sessionId={sessionId} turn={turn} attempts={attempts} cutoffRank={cutoffRank} />
      ) : (
        <ToolPayloads sessionId={sessionId} turn={turn} tool={tool} cutoffRank={cutoffRank} />
      )}
    </article>
  );
}
