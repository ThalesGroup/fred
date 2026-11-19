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
import { Link, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import { ConversationTraceHistory } from "./ConversationTraceHistory";
import { useGetConversationTraceQuery } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  TRACE_LIST_PATH,
  TRACE_TRANSLATION_PREFIX,
  TraceIdentifier,
  TraceOutcomeBadge,
  TracePageButtons,
  useTracePagination,
} from "./traceControls";
import styles from "./ConversationTraces.module.css";

export default function ConversationTraceInspectorPage() {
  const { sessionId } = useParams();
  return <ConversationTraceInspector key={sessionId} sessionId={sessionId} />;
}

function ConversationTraceInspector({ sessionId }: { sessionId: string | undefined }) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const [selectedExchange, setSelectedExchange] = useState<string>();
  const pager = useTracePagination();
  const trace = useGetConversationTraceQuery(sessionId ? { sessionId, cursor: pager.cursor } : skipToken, {
    refetchOnMountOrArgChange: true,
    refetchOnFocus: true,
  });
  const conversation = trace.currentData;
  const turn =
    conversation?.turns.find(({ exchange_id }) => exchange_id === selectedExchange) ?? conversation?.turns[0];
  const cutoff = conversation?.consent_cutoff;
  const conversationAccess = conversation?.local_content_access
    ? t("localAccess")
    : cutoff
      ? t("sharedThrough", { number: cutoff.turn_number })
      : t("masked");
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "medium" });
  const duration = new Intl.NumberFormat(i18n.language, { style: "unit", unit: "millisecond" });
  const missing = trace.isError && "status" in trace.error && trace.error.status === 404;

  return (
    <div className={styles.page}>
      <PageHeader
        title={t(cutoff || conversation?.local_content_access ? "conversation" : "maskedConversation")}
        subtitle={conversation?.agent_display_name}
        breadcrumb={
          <Link className={styles.link} to={TRACE_LIST_PATH}>
            {t("title")}
          </Link>
        }
      />
      {trace.isError ? (
        <p role="alert" className={styles.error}>
          {t(missing ? "notFound" : "inspectorError")}
        </p>
      ) : conversation ? (
        <>
          <div className={styles.conversationSummary}>
            <div>
              <span>{t("conversationId")}</span>
              <TraceIdentifier label={t("conversationId")} value={conversation.session_id} />
            </div>
            <div>
              <span>{t("teamId")}</span>
              <TraceIdentifier label={t("teamId")} value={conversation.team_id} />
            </div>
            <span className={styles.outcome}>{conversationAccess}</span>
          </div>
          {turn ? (
            <div className={styles.inspector}>
              <section className={styles.turns} aria-label={t("turns")}>
                <h2>{t("turns")}</h2>
                <ul>
                  {conversation.turns.map((item) => (
                    <li key={item.exchange_id}>
                      <button
                        type="button"
                        className={styles.turnButton}
                        aria-pressed={item.exchange_id === turn.exchange_id}
                        onClick={() => setSelectedExchange(item.exchange_id)}
                      >
                        <strong>
                          {item.turn_number ? t("turnNumber", { number: item.turn_number }) : t("capturedTurn")}
                        </strong>
                        <time dateTime={item.started_at}>{date.format(new Date(item.started_at))}</time>
                        <TraceOutcomeBadge outcome={item.outcome} />
                        {item.availability === "history_only" && <small>{t("evidence.history_only")}</small>}
                        {(cutoff || conversation.local_content_access) && (
                          <small>{t(`access.${item.access ?? "masked"}`)}</small>
                        )}
                      </button>
                    </li>
                  ))}
                </ul>
                <TracePageButtons pager={pager} nextCursor={conversation.next_cursor} disabled={trace.isFetching} />
              </section>
              <section className={styles.turnDetail} aria-label={t("turnSummary")}>
                <header>
                  <h2>{t("turnSummary")}</h2>
                  <TraceOutcomeBadge outcome={turn.outcome} />
                </header>
                <dl>
                  <dt>{t("availability")}</dt>
                  <dd>{t(`evidence.${turn.availability}`)}</dd>
                  <dt>{t("startedAt")}</dt>
                  <dd>
                    <time dateTime={turn.started_at}>{date.format(new Date(turn.started_at))}</time>
                  </dd>
                  <dt>{t("duration")}</dt>
                  <dd>{turn.duration_ms != null ? duration.format(turn.duration_ms) : t("unavailable")}</dd>
                  <dt>{t("exchangeId")}</dt>
                  <dd>
                    <TraceIdentifier label={t("exchangeId")} value={turn.exchange_id} />
                  </dd>
                  {turn.trace_id && (
                    <>
                      <dt>{t("traceId")}</dt>
                      <dd>
                        <TraceIdentifier label={t("traceId")} value={turn.trace_id} />
                      </dd>
                    </>
                  )}
                  {turn.span_id && (
                    <>
                      <dt>{t("spanId")}</dt>
                      <dd>
                        <TraceIdentifier label={t("spanId")} value={turn.span_id} />
                      </dd>
                    </>
                  )}
                  {turn.call_ids.length > 0 && (
                    <>
                      <dt>{t("callIds")}</dt>
                      <dd>
                        <ul className={styles.calls}>
                          {turn.call_ids.map((id) => (
                            <li key={id}>
                              <TraceIdentifier label={t("callId")} value={id} />
                            </li>
                          ))}
                        </ul>
                      </dd>
                    </>
                  )}
                </dl>
                <ConversationTraceHistory key={turn.exchange_id} sessionId={conversation.session_id} turn={turn} />
              </section>
            </div>
          ) : (
            <p role="status" className={styles.empty}>
              {t("historyUnavailable")}
            </p>
          )}
        </>
      ) : (
        <p className={styles.empty} role="status">
          {t("loading")}
        </p>
      )}
    </div>
  );
}
