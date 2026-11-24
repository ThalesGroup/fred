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

import { type ReactElement, useMemo, useState } from "react";
import { skipToken } from "@reduxjs/toolkit/query";
import { Link, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import Chip from "@shared/atoms/Chip/Chip";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import PageHeader from "@shared/molecules/PageHeader/PageHeader";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  type ConversationTraceTurn,
  type OtlpTraceSpan,
  type TraceHttpAttempt,
  type TraceModelCall,
  type TraceToolCall,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import { ConversationTraceModelCall } from "./ConversationTraceHttp";
import { ConversationTraceSse } from "./ConversationTraceSse";
import { ConversationTraceHistory } from "./ConversationTraceHistory";
import { ConversationTraceOverview } from "./ConversationTraceOverview";
import { ConversationTraceTool } from "./ConversationTraceTool";
import { RecordTraceConsent } from "./RecordTraceConsent";
import { TraceDeleteButton } from "./TraceDeleteButton";
import { TraceExportButton } from "./TraceExportButton";
import {
  TRACE_LIST_PATH,
  TRACE_TRANSLATION_PREFIX,
  TraceFact,
  TraceIdentifier,
  TraceInspectorLink,
  TraceOutcomeBadge,
  TracePageButtons,
  nextTraceInspectorState,
  traceElapsedFormatter,
  traceInspectorOrigin,
} from "./traceControls";
import styles from "./ConversationTraces.module.css";

type Call =
  | { kind: "llm"; ref: string; attempt?: TraceHttpAttempt; model?: TraceModelCall }
  | { kind: "tool"; ref: string; tool: TraceToolCall };

type CallNode = { call: Call; children: CallNode[] };

const refresh = { refetchOnMountOrArgChange: true, refetchOnFocus: true };
const callsPerPage = 50;

function indexCallTree(roots: CallNode[]) {
  const positions = new Map<string, { start: number; end: number }>();
  let count = 0;
  function index(node: CallNode) {
    const start = count++;
    node.children.forEach(index);
    positions.set(node.call.ref, { start, end: count });
  }
  roots.forEach(index);
  return { count, positions };
}

function callTreePage(roots: CallNode[], positions: ReturnType<typeof indexCallTree>["positions"], page: number) {
  const start = page * callsPerPage;
  const end = start + callsPerPage;
  function select(node: CallNode): CallNode[] {
    const position = positions.get(node.call.ref);
    if (!position || position.start >= end || position.end <= start) return [];
    return [{ call: node.call, children: node.children.flatMap(select) }];
  }
  return roots.flatMap(select);
}

function lastFailedModelCall(calls: Call[]) {
  for (let index = calls.length - 1; index >= 0; index--) {
    const call = calls[index];
    if (call.kind === "llm" && (call.attempt?.failure_stage || (call.attempt?.status ?? 0) >= 400)) {
      return call;
    }
  }
}

function capturedEvidenceState(turn: ConversationTraceTurn) {
  return turn.capture_status === "complete" ? "captured" : (turn.capture_status ?? turn.availability);
}

function turnCalls(
  attempts: TraceHttpAttempt[],
  models: TraceModelCall[],
  tools: TraceToolCall[],
  spans: OtlpTraceSpan[],
): { calls: Call[]; roots: CallNode[] } {
  const modelByCall = new Map(models.map((model) => [model.call_id, model]));
  const callsWithHttp = new Set(attempts.map(({ call_id }) => call_id));
  const modelCalls = [
    ...attempts.map((attempt) => ({
      kind: "llm" as const,
      ref: attempt.ref,
      attempt,
      model: modelByCall.get(attempt.call_id),
      callId: attempt.call_id,
    })),
    ...models
      .filter((model) => !callsWithHttp.has(model.call_id))
      .map((model) => ({
        kind: "llm" as const,
        ref: model.ref,
        model,
        callId: model.call_id,
      })),
  ];
  if (spans.length) {
    const calls: Call[] = [...modelCalls, ...tools.map((tool) => ({ kind: "tool" as const, ref: tool.ref, tool }))];
    return { calls, roots: spanTree(calls, spans) };
  }
  const lastRefByCall = new Map(modelCalls.map(({ callId, ref }) => [callId, ref]));
  const toolsByRequest = new Map<string | undefined, Call[]>();
  for (const tool of tools) {
    const request = tool.model_calls?.find(({ relation }) => relation === "requested");
    const ref = request ? lastRefByCall.get(request.call_id) : undefined;
    const siblings = toolsByRequest.get(ref) ?? [];
    siblings.push({ kind: "tool", ref: tool.ref, tool });
    toolsByRequest.set(ref, siblings);
  }
  const calls = [
    ...modelCalls.flatMap((call) => [call, ...(toolsByRequest.get(call.ref) ?? [])]),
    ...(toolsByRequest.get(undefined) ?? []),
  ];
  return { calls, roots: calls.map((call) => ({ call, children: [] })) };
}

function spanTree(calls: Call[], spans: OtlpTraceSpan[]): CallNode[] {
  const modelCalls = new Map<string, Call[]>();
  const tools = new Map<string, Call>();
  for (const call of calls) {
    if (call.kind === "tool") {
      tools.set(call.ref, call);
    } else {
      const id = call.attempt?.call_id ?? call.model?.call_id;
      if (id) {
        const attempts = modelCalls.get(id) ?? [];
        attempts.push(call);
        modelCalls.set(id, attempts);
      }
    }
  }
  const key = (traceId: string, spanId: string) => `${traceId}:${spanId}`;
  const byId = new Map(spans.map((span) => [key(span.traceId, span.spanId), span]));
  const ordered = [...spans].sort((a, b) => {
    const left = a.startTimeUnixNano;
    const right = b.startTimeUnixNano;
    return left.length - right.length || left.localeCompare(right);
  });
  const displayed = new Set<string>();
  const bySpan = new Map<string, CallNode[]>();
  for (const span of ordered) {
    const attributes = new Map(span.attributes?.map(({ key, value }) => [key, value.stringValue]));
    const toolRef = attributes.get("fred.evidence.ref");
    const modelId = attributes.get("fred.call.id");
    const tool = toolRef ? tools.get(toolRef) : undefined;
    const matches = tool ? [tool] : modelId ? (modelCalls.get(modelId) ?? []) : [];
    const nodes = matches.flatMap((call) => {
      if (displayed.has(call.ref)) return [];
      displayed.add(call.ref);
      return [{ call, children: [] }];
    });
    if (nodes.length) bySpan.set(key(span.traceId, span.spanId), nodes);
  }

  const roots: CallNode[] = [];
  for (const [id, nodes] of bySpan) {
    let span = byId.get(id);
    let parent: CallNode | undefined;
    const visited = new Set([id]);
    // Runtime spans with no visible call can still carry the parent relationship.
    while (span?.parentSpanId) {
      const ancestor = key(span.traceId, span.parentSpanId);
      if (visited.has(ancestor)) {
        parent = undefined;
        break;
      }
      visited.add(ancestor);
      const parentNodes = bySpan.get(ancestor);
      parent ??= parentNodes?.[parentNodes.length - 1];
      span = byId.get(ancestor);
    }
    (parent?.children ?? roots).push(...nodes);
  }
  for (const call of calls) {
    if (!displayed.has(call.ref)) roots.push({ call, children: [] });
  }
  return roots;
}

function useTurnCalls(sessionId: string | undefined, turn?: ConversationTraceTurn) {
  const args =
    sessionId && turn && turn.availability !== "history_only" ? { sessionId, exchangeId: turn.exchange_id } : skipToken;
  const http = enhancedControlPlaneApi.useListConversationTraceHttpAttemptsQuery(args, refresh);
  const models = enhancedControlPlaneApi.useListConversationTraceModelCallsQuery(args, refresh);
  const tools = enhancedControlPlaneApi.useListConversationTraceToolCallsQuery(args, refresh);
  const spans = enhancedControlPlaneApi.useListConversationTraceSpansQuery(args, refresh);
  const attempts = http.isError ? undefined : http.currentData;
  const modelCalls = models.isError ? undefined : models.currentData;
  const toolCalls = tools.isError ? undefined : tools.currentData;
  const spanData = spans.isError ? undefined : spans.currentData;
  const tree = useMemo(
    () => turnCalls(attempts ?? [], modelCalls ?? [], toolCalls ?? [], spanData ?? []),
    [attempts, modelCalls, toolCalls, spanData],
  );
  return {
    ...tree,
    loading: [http, models, tools].some((query) => query.isFetching && !query.currentData),
    failed: http.isError || models.isError || tools.isError,
    refetch: () => {
      if (args === skipToken) return;
      void http.refetch();
      void models.refetch();
      void tools.refetch();
      void spans.refetch();
    },
  };
}

function pageCursor(params: URLSearchParams) {
  const cursor = params.get("cursor");
  if (cursor) {
    const separator = cursor.indexOf("|");
    const rank = cursor.slice(0, separator);
    const exchange = cursor.slice(separator + 1);
    if (
      separator > 0 &&
      /^[0-9]{1,10}$/.test(rank) &&
      +rank < 2 ** 31 &&
      exchange.length >= 1 &&
      exchange.length <= 255
    ) {
      return cursor;
    }
  }
  const rank = params.get("rank");
  if (rank && /^[0-9]{1,10}$/.test(rank) && +rank > 0 && +rank < 2 ** 31) {
    return String(+rank - 1) + "|_";
  }
}

export default function ConversationTraceInspectorPage() {
  const { sessionId } = useParams();
  return <ConversationTraceInspector key={sessionId} sessionId={sessionId} />;
}

function ConversationTraceInspector({ sessionId }: { sessionId?: string }) {
  const navigate = useNavigate();
  const { state } = useLocation();
  const origin = traceInspectorOrigin(state);
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const [params, setParams] = useSearchParams();
  const [expandedTurns, setExpandedTurns] = useState<Record<string, boolean>>({});
  const [previousPages, setPreviousPages] = useState(new Map<string, string | undefined>());
  const cursor = pageCursor(params);
  const trace = enhancedControlPlaneApi.useGetConversationTraceQuery(
    sessionId ? { sessionId, cursor } : skipToken,
    refresh,
  );
  const conversation = trace.isError ? undefined : trace.currentData;
  const requestedTurn = params.get("turn");
  const recentTurns = conversation?.turns.slice().reverse();
  const turn = requestedTurn
    ? conversation?.turns.find(({ exchange_id }) => exchange_id === requestedTurn)
    : (recentTurns?.find((item) => item.outcome === "failed" || item.failure_category) ?? recentTurns?.[0]);
  const callData = useTurnCalls(sessionId, turn);
  const { calls, loading: loadingCalls } = callData;
  const failedCall = turn?.outcome === "failed" || turn?.failure_category ? lastFailedModelCall(calls) : undefined;
  const requestedCall = params.get("call");
  const view = params.get("view");
  const selectedCall = requestedCall
    ? (calls.find(({ ref }) => requestedCall === ref) ??
      calls.find(
        (call) =>
          call.kind === "llm" &&
          (requestedCall === call.model?.ref ||
            requestedCall === call.model?.call_id ||
            requestedCall === call.attempt?.call_id),
      ))
    : (failedCall ?? calls.find((call) => call.kind === "llm" && (call.attempt?.status ?? 0) >= 400) ?? calls[0]);
  const showTurn = view === "history" || !selectedCall;
  const turnTimeline = view === "sse" && !requestedCall && turn?.availability !== "history_only";
  const cutoff = conversation?.consent_cutoff;
  const time = new Intl.DateTimeFormat(i18n.language, { timeStyle: "medium" });
  const missing = trace.isError && "status" in trace.error && trace.error.status === 404;

  function callSearch(exchange: string, ref?: string, tab?: string) {
    const next = new URLSearchParams(params);
    next.set("turn", exchange);
    if (ref) next.set("call", ref);
    else next.delete("call");
    if (tab) next.set("view", tab);
    else next.delete("view");
    return next;
  }

  function selectPage(anchor?: string) {
    setParams(anchor ? { cursor: anchor } : {}, { preventScrollReset: true, state: nextTraceInspectorState(origin) });
  }

  const pager = {
    cursor,
    next: (anchor: string) => {
      setPreviousPages((pages) => new Map(pages).set(anchor, cursor));
      selectPage(anchor);
    },
    previous: () => selectPage(cursor ? previousPages.get(cursor) : undefined),
  };

  function selectView(tab: string) {
    if (turn && selectedCall) {
      setParams(callSearch(turn.exchange_id, selectedCall.ref, tab), {
        replace: true,
        preventScrollReset: true,
        state: origin,
      });
    }
  }

  const breadcrumb = (
    <Link
      className={styles.back}
      to={{ pathname: TRACE_LIST_PATH, search: origin?.listSearch }}
      onClick={(event) => {
        if (!origin || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
        event.preventDefault();
        void navigate(-origin.listSteps);
      }}
    >
      <Icon category="outlined" type="arrow_back" />
      {t("title")}
    </Link>
  );

  return (
    <div className={styles.page}>
      <PageHeader
        title={t("inspectorTitle")}
        breadcrumb={breadcrumb}
        actions={
          conversation && (
            <div className={styles.chips}>
              {turn?.capture_status === "saving" && (
                <Button
                  size="small"
                  color="secondary"
                  variant="outlined"
                  disabled={trace.isFetching || loadingCalls}
                  onClick={() => {
                    void trace.refetch();
                    callData.refetch();
                  }}
                >
                  {t("refresh")}
                </Button>
              )}
              <TraceExportButton single sessionIds={[conversation.session_id]} />
              {!conversation.retained_after_delete && (
                <RecordTraceConsent
                  conversation={conversation}
                  selectedExchange={turn?.exchange_id}
                  onConflict={() => void trace.refetch()}
                />
              )}
              <TraceDeleteButton
                mode="selected"
                single
                sessionIds={[conversation.session_id]}
                onDeleted={() => navigate(TRACE_LIST_PATH)}
              />
            </div>
          )
        }
      />
      {conversation && <ConversationTraceOverview conversation={conversation} />}
      {trace.isError ? (
        missing ? (
          <PageEmptyState message={t("notFound")} icon="search" />
        ) : (
          <p role="alert" className={styles.error}>
            {t("inspectorError")}
          </p>
        )
      ) : !conversation ? (
        <p role="status" className={styles.empty}>
          {t("loading")}
        </p>
      ) : conversation.turns.length === 0 && !cursor ? (
        <PageEmptyState message={t("historyUnavailable")} icon="search" />
      ) : (
        <div className={styles.inspector}>
          <nav className={styles.tree} aria-label={t("callTree")}>
            <header>
              <h2>{t("callTree")}</h2>
            </header>
            {conversation.turns.map((item, index) => {
              const current = item.exchange_id === turn?.exchange_id;
              const evidenceState = capturedEvidenceState(item);
              // Keep the opening fan-out bounded on long conversations.
              const open = expandedTurns[item.exchange_id] ?? (current || index < 3);
              return (
                <section className={styles.treeTurn} key={item.exchange_id}>
                  <h3>
                    <button
                      type="button"
                      className={styles.turnToggle}
                      aria-expanded={open}
                      onClick={() => setExpandedTurns((previous) => ({ ...previous, [item.exchange_id]: !open }))}
                    >
                      <Icon category="outlined" type={open ? "expand_more" : "chevron_right"} />
                      <strong>
                        {item.turn_number != null ? t("turnNumber", { number: item.turn_number }) : t("capturedTurn")}
                      </strong>
                      {item.access !== "shared" && item.access !== "local" && <Icon category="outlined" type="lock" />}
                      <time dateTime={item.started_at}>{time.format(new Date(item.started_at))}</time>
                    </button>
                  </h3>
                  <div className={styles.turnOutcome}>
                    <TraceOutcomeBadge outcome={item.failure_category ?? item.outcome} />
                    {evidenceState !== "captured" && (
                      <small role={current && evidenceState === "saving" ? "status" : undefined}>
                        {t(`evidence.${evidenceState}`)}
                      </small>
                    )}
                    {evidenceState === "partial" && item.degradation_reason && (
                      <small>{t(`degradation.${item.degradation_reason}`)}</small>
                    )}
                  </div>
                  {open && (
                    <TurnTreeLinks
                      sessionId={conversation.session_id}
                      turn={item}
                      metadata={current ? callData : undefined}
                      selectedRef={current && !showTurn && !turnTimeline ? selectedCall?.ref : undefined}
                      failedRef={current ? failedCall?.ref : undefined}
                      selectedView={
                        current && (showTurn || turnTimeline) && !requestedCall
                          ? turnTimeline
                            ? "sse"
                            : "history"
                          : undefined
                      }
                      callSearch={callSearch}
                    />
                  )}
                </section>
              );
            })}
            <TracePageButtons pager={pager} nextCursor={conversation.next_cursor} disabled={trace.isFetching} />
          </nav>
          {!turn ? (
            <p className={styles.evidence} role="status">
              {t("turnUnavailable")}
            </p>
          ) : loadingCalls && view !== "history" && (!requestedCall || !selectedCall) ? (
            <p className={styles.evidence} role="status">
              {t("loadingCalls")}
            </p>
          ) : requestedCall && !selectedCall ? (
            <p className={styles.evidence} role="status">
              {t("callUnavailable")}
            </p>
          ) : turnTimeline && turn.availability !== "history_only" ? (
            <article className={styles.evidence}>
              <ConversationTraceSse
                key={turn.exchange_id}
                sessionId={conversation.session_id}
                turn={turn}
                cutoffRank={cutoff?.last_rank}
              />
            </article>
          ) : showTurn || !selectedCall ? (
            <TurnEvidence key={turn.exchange_id} sessionId={conversation.session_id} turn={turn} />
          ) : selectedCall.kind === "tool" ? (
            <ConversationTraceTool
              key={selectedCall.ref}
              sessionId={conversation.session_id}
              turn={turn}
              tool={selectedCall.tool}
              cutoffRank={cutoff?.last_rank}
              view={view}
              onView={selectView}
              onModelCall={(call) =>
                setParams(callSearch(turn.exchange_id, call, "langchain"), {
                  preventScrollReset: true,
                  state: nextTraceInspectorState(origin),
                })
              }
            />
          ) : (
            <ConversationTraceModelCall
              key={selectedCall.ref}
              sessionId={conversation.session_id}
              turn={turn}
              attempt={selectedCall.attempt}
              model={selectedCall.model}
              cutoffRank={cutoff?.last_rank}
              view={view}
              onView={selectView}
            />
          )}
        </div>
      )}
    </div>
  );
}

function TurnTreeLinks({
  sessionId,
  turn,
  metadata,
  selectedRef,
  failedRef,
  selectedView,
  callSearch,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  metadata?: ReturnType<typeof useTurnCalls>;
  selectedRef?: string;
  failedRef?: string;
  selectedView?: "sse" | "history";
  callSearch: (exchange: string, ref?: string, tab?: string) => URLSearchParams;
}) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const elapsed = traceElapsedFormatter(i18n.language);
  const inactive = useTurnCalls(sessionId, metadata ? undefined : turn);
  const { roots, loading, failed } = metadata ?? inactive;
  const search = (ref?: string, view?: string) => callSearch(turn.exchange_id, ref, view).toString();
  const [pageChoice, setPageChoice] = useState<{ selectedRef?: string; page: number }>();
  const { count, positions } = useMemo(() => indexCallTree(roots), [roots]);
  const selectionPage = Math.floor((positions.get(selectedRef ?? "")?.start ?? 0) / callsPerPage);
  const lastPage = Math.max(0, Math.ceil(count / callsPerPage) - 1);
  const page = Math.min(
    lastPage,
    pageChoice && pageChoice.selectedRef === selectedRef ? pageChoice.page : selectionPage,
  );
  const visibleRoots = callTreePage(roots, positions, page);
  const selectPage = (page: number) => setPageChoice({ selectedRef, page });

  function renderCall({ call, children }: CallNode): ReactElement {
    const model = call.kind === "llm";
    const name = model
      ? (call.attempt?.model ?? call.model?.model ?? t("http.modelCall"))
      : (call.tool.tool_name ?? t("tool.unnamed"));
    const duration = model ? call.attempt?.duration_ms : call.tool.duration_ms;
    const detail = model ? t("llm") : t(`tool.sources.${call.tool.source}`);
    const attempts = call.kind === "tool" ? call.tool.http_attempts : undefined;
    const status = model ? call.attempt?.status : attempts?.[attempts.length - 1]?.status;
    const failureStage = model ? call.attempt?.failure_stage : undefined;
    return (
      <li key={call.ref}>
        <TraceInspectorLink
          className={styles.callLink}
          search={search(call.ref)}
          aria-current={call.ref === selectedRef ? "true" : undefined}
        >
          <Icon category="outlined" type={model ? "smart_toy" : "build"} />
          <span className={styles.callLabel}>
            <strong>{name}</strong>
            <span>{duration == null ? detail : detail + " · " + elapsed(duration)}</span>
            {failureStage && <span className={styles.callFailure}>{t(`http.stage.${failureStage}`)}</span>}
          </span>
          {status != null && (
            <span className={styles.callStatus} data-failed={status >= 400}>
              {status}
            </span>
          )}
        </TraceInspectorLink>
        {children.length > 0 && <ul>{children.map(renderCall)}</ul>}
      </li>
    );
  }

  return (
    <>
      {failed && (
        <p role="status" className={styles.treeStatus}>
          {t("callsUnavailable")}
        </p>
      )}
      {loading && (
        <p role="status" className={styles.treeStatus}>
          {t("loadingCalls")}
        </p>
      )}
      <ul>
        {failedRef && failedRef !== selectedRef && (
          <li>
            <TraceInspectorLink className={styles.callLink} search={search(failedRef)}>
              <Icon category="outlined" type="error_outline" />
              {t("jumpToFailedCall")}
            </TraceInspectorLink>
          </li>
        )}
        {visibleRoots.map(renderCall)}
        <li>
          <TraceInspectorLink
            className={styles.callLink}
            search={search(undefined, "history")}
            aria-current={selectedView === "history" ? "true" : undefined}
          >
            <Icon category="outlined" type="description" />
            <span className={styles.callLabel}>{t("savedHistory")}</span>
          </TraceInspectorLink>
        </li>
        {!loading && turn.availability !== "history_only" && (
          <li>
            <TraceInspectorLink
              className={styles.callLink}
              search={search(undefined, "sse")}
              aria-current={selectedView === "sse" ? "true" : undefined}
            >
              <Icon category="outlined" type="show_chart" />
              <span className={styles.callLabel}>{t("sse.turnTimeline")}</span>
            </TraceInspectorLink>
          </li>
        )}
      </ul>
      <TracePageButtons
        label={t("callPages")}
        pager={{
          cursor: page > 0 ? String(page) : undefined,
          previous: () => selectPage(page - 1),
          next: (cursor) => selectPage(Number(cursor)),
        }}
        nextCursor={page < lastPage ? String(page + 1) : null}
        disabled={loading}
      />
    </>
  );
}

function TurnEvidence({ sessionId, turn }: { sessionId: string; turn: ConversationTraceTurn }) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: TRACE_TRANSLATION_PREFIX });
  const date = new Intl.DateTimeFormat(i18n.language, { dateStyle: "medium", timeStyle: "medium" });
  const evidenceState = capturedEvidenceState(turn);
  return (
    <article className={styles.evidence} aria-label={t("turnSummary")}>
      <header className={styles.evidenceHeader}>
        <h2>{turn.turn_number != null ? t("turnNumber", { number: turn.turn_number }) : t("capturedTurn")}</h2>
        <div className={styles.chips}>
          <TraceOutcomeBadge outcome={turn.failure_category ?? turn.outcome} />
          <Chip label={t(`evidence.${evidenceState}`)} />
          <Chip label={t(`access.${turn.access ?? "masked"}`)} />
        </div>
      </header>
      {evidenceState === "partial" && turn.degradation_reason && (
        <p className={styles.help}>{t(`degradation.${turn.degradation_reason}`)}</p>
      )}
      <dl className={styles.callSummary}>
        <TraceFact label={t("startedAt")}>
          <time dateTime={turn.started_at}>{date.format(new Date(turn.started_at))}</time>
        </TraceFact>
        <TraceFact label={t("duration")}>
          {turn.duration_ms != null ? traceElapsedFormatter(i18n.language)(turn.duration_ms) : t("unavailable")}
        </TraceFact>
        {[
          ["exchangeId", turn.exchange_id],
          ["traceId", turn.trace_id],
          ["spanId", turn.span_id],
          [
            "supportErrorRef",
            turn.reported_failures?.some(({ support_error_ref }) => support_error_ref === turn.support_error_ref)
              ? null
              : turn.support_error_ref,
          ],
        ].map(
          ([label, id]) =>
            id &&
            label && (
              <TraceFact key={label} label={t(label)}>
                <TraceIdentifier label={t(label)} value={id} />
              </TraceFact>
            ),
        )}
        {turn.reported_failures?.map(({ support_error_ref, failure_category }) => (
          <TraceFact key={support_error_ref} label={t("supportErrorRef")}>
            <TraceIdentifier label={t("supportErrorRef")} value={support_error_ref} />
            <TraceOutcomeBadge outcome={failure_category ?? "failed"} />
          </TraceFact>
        ))}
        {turn.call_ids.length > 0 && (
          <TraceFact label={t("callIds")}>
            {turn.call_ids.map((id) => (
              <TraceIdentifier key={id} label={t("callId")} value={id} />
            ))}
          </TraceFact>
        )}
      </dl>
      <ConversationTraceHistory sessionId={sessionId} turn={turn} />
    </article>
  );
}
