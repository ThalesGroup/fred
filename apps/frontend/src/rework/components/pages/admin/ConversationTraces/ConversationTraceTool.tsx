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
import { skipToken } from "@reduxjs/toolkit/query";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import ButtonGroup from "@shared/atoms/ButtonGroup/ButtonGroup";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ConversationTraceTurn,
  TraceHttpAttempt,
  TraceToolCall,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { TraceHttpAttemptEvidence, TraceHttpAttemptSummary } from "./ConversationTraceHttp";
import TraceJson from "./TraceJson";
import { TRACE_TRANSLATION_PREFIX, TraceIdentifier, canReadTraceArtifact } from "./traceControls";
import styles from "./ConversationTraces.module.css";

const prefix = TRACE_TRANSLATION_PREFIX + ".tool";

export function ConversationTraceToolTree({
  calls,
  activeRef,
  onSelect,
  unavailable,
}: {
  calls: TraceToolCall[];
  activeRef?: string;
  onSelect: (ref: string) => void;
  unavailable: boolean;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  if (unavailable) return <p role="status">{t("summaryUnavailable")}</p>;
  if (calls.length === 0) return null;
  return (
    <ul className={styles.turnTools} aria-label={t("title")}>
      {calls.map((call) => {
        const name = call.tool_name ?? t("unnamed");
        const summary = t("attemptOutcome", { number: call.attempt, outcome: t("outcomes." + call.outcome) });
        return (
          <li key={call.ref}>
            <button
              className={styles.turnButton}
              type="button"
              aria-label={t("callLabel", { name, summary })}
              aria-pressed={call.ref === activeRef}
              onClick={() => onSelect(call.ref)}
            >
              <strong>{name}</strong>
              <small>{summary}</small>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

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
  const query = enhancedControlPlaneApi.useGetConversationTraceToolEvidenceQuery(
    canRead && tool.completeness !== "unavailable"
      ? { sessionId, exchangeId: turn.exchange_id, ref: tool.ref }
      : skipToken,
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  if (!canRead) return <p>{t("masked")}</p>;
  if (tool.completeness === "unavailable" || query.isError) return <p>{t("unavailable")}</p>;
  const evidence = query.currentData;
  if (!evidence) return <p role="status">{t("loading")}</p>;
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
      <TraceHttpAttemptSummary active={active} />
      <TraceHttpAttemptEvidence sessionId={sessionId} turn={turn} attempt={active} cutoffRank={cutoffRank} />
    </div>
  );
}

export function ConversationTraceTool({
  sessionId,
  turn,
  tool,
  cutoffRank,
  onModelCall,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  tool: TraceToolCall;
  cutoffRank?: number;
  onModelCall: (callId: string) => void;
}) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: prefix });
  const [view, setView] = useState(0);
  const milliseconds = new Intl.NumberFormat(i18n.language, { style: "unit", unit: "millisecond" });
  const attempts = tool.http_attempts ?? [];
  return (
    <section className={styles.history} aria-label={t("title")}>
      <h3>{tool.tool_name ?? t("unnamed")}</h3>
      <dl>
        <dt>{t("source")}</dt>
        <dd>{t("sources." + tool.source)}</dd>
        <dt>{t("outcome")}</dt>
        <dd>
          <span className={styles.outcome} data-outcome={tool.outcome === "error" ? "failed" : tool.outcome}>
            {t("outcomes." + tool.outcome)}
          </span>
        </dd>
        <dt>{t("attempt")}</dt>
        <dd>{tool.attempt}</dd>
        <dt>{t("duration")}</dt>
        <dd>{milliseconds.format(tool.duration_ms)}</dd>
        {tool.call_id && (
          <>
            <dt>{t("callId")}</dt>
            <dd>
              <TraceIdentifier label={t("callId")} value={tool.call_id} />
            </dd>
          </>
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
        <ButtonGroup
          items={[{ label: t("inputOutput") }, { label: t("http") }]}
          size="2xs"
          color="primary"
          variant="tabs"
          aria-label={t("tabs")}
          selectedIndex={view}
          onSelectedIndexChange={setView}
        />
      )}
      {view === 1 && attempts.length > 0 ? (
        <ToolHttp sessionId={sessionId} turn={turn} attempts={attempts} cutoffRank={cutoffRank} />
      ) : (
        <ToolPayloads sessionId={sessionId} turn={turn} tool={tool} cutoffRank={cutoffRank} />
      )}
    </section>
  );
}
