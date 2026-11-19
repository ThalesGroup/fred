// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { skipToken } from "@reduxjs/toolkit/query";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import Button from "@shared/atoms/Button/Button";
import { CodeBlock } from "@shared/molecules/CodeBlock/CodeBlock";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ConversationTraceTurn,
  TraceSseEvent,
  TraceSseKind,
  TraceSseLane,
  TraceSseSegment,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import SseWindow, { type SseRange } from "./SseWindow";
import { formatTraceJson } from "./formatTraceJson";
import {
  TRACE_TRANSLATION_PREFIX,
  canReadTraceArtifact,
  downloadTraceBytes,
  traceElapsedFormatter,
  traceBytes,
} from "./traceControls";
import TraceJson from "./TraceJson";
import styles from "./ConversationTraces.module.css";

type TrackSource = "provider" | "outgoing";
type Lane = { stream: TraceSseLane; shared: boolean };
type TimedFrame = {
  source: TrackSource;
  frame: TraceSseEvent;
  ref: string;
  index: number;
  key: string;
  shared: boolean;
};

const prefix = TRACE_TRANSLATION_PREFIX + ".sse";
const trackSources = ["provider", "outgoing"] as const;
const eventKinds: TraceSseKind[] = ["text", "reasoning", "tool", "status", "done", "error", "other"];

function trackFrames(source: TrackSource, lanes: Lane[]): TimedFrame[] {
  return lanes.flatMap(({ stream, shared }) =>
    stream.frames.map((frame, index) => ({
      source,
      frame,
      ref: stream.ref,
      index,
      shared,
      key: stream.ref + "-" + index,
    })),
  );
}

function longestGap(lanes: Lane[]) {
  return lanes.reduce<[number, number] | undefined>((largest, { stream }) => {
    const gap = stream.longest_gap;
    return gap && (!largest || gap[1] - gap[0] > largest[1] - largest[0]) ? gap : largest;
  }, undefined);
}

export function TraceSseFramePayload({
  sessionId,
  exchangeId,
  refId,
  index,
  shared,
  stored,
}: {
  sessionId: string;
  exchangeId: string;
  refId: string;
  index: number;
  shared: boolean;
  stored: boolean;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const [showRaw, setShowRaw] = useState(false);
  const canRead = shared && stored;
  const response = enhancedControlPlaneApi.useGetConversationTraceSseFrameQuery(
    canRead ? { sessionId, exchangeId, ref: refId, index } : skipToken,
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  if (!shared) return <p>{t("masked")}</p>;
  if (!canRead || response.isError) return <p>{t("frameUnavailable")}</p>;
  if (!response.currentData || response.isFetching) return <p role="status">{t("loading")}</p>;

  const original = response.currentData.data;
  const raw = new TextDecoder("utf-8", { ignoreBOM: true }).decode(traceBytes(original));
  const data = raw
    .replace(/^\uFEFF/, "")
    .split(/\r\n?|\n/)
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).replace(/^ /, ""))
    .join("\n");
  const json = formatTraceJson(data);
  return (
    <>
      <div className={styles.sseControls}>
        {json && (
          <Button type="button" size="2xs" variant="text" color="on-surface" onClick={() => setShowRaw(!showRaw)}>
            {t(showRaw ? "viewJson" : "viewRaw")}
          </Button>
        )}
        <Button
          type="button"
          size="2xs"
          variant="text"
          color="on-surface"
          onClick={() => downloadTraceBytes(original, "sse-frame.bin")}
        >
          {t("download")}
        </Button>
      </div>
      {json && !showRaw ? (
        <TraceJson code={json} label={t("frame")} copyText={data} />
      ) : (
        <div className={styles.rawBody} tabIndex={0} aria-label={t("frame")}>
          <CodeBlock code={raw} language="text" highlight={false} />
        </div>
      )}
    </>
  );
}

function SseTrack({
  source,
  lanes,
  sessionId,
  exchangeId,
  events,
  view,
  selected,
  select,
  elapsed,
}: {
  source: TrackSource;
  lanes: Lane[];
  sessionId: string;
  exchangeId: string;
  events: TimedFrame[];
  view: SseRange;
  selected: string | undefined;
  select: (key: string) => void;
  elapsed: (ms: number) => string;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const gap = longestGap(lanes);
  const first = lanes[0]?.stream;
  const last = lanes[lanes.length - 1]?.stream;
  const inView = (ms: number) => ms >= view.start && ms <= view.end;
  const percent = (ms: number) => (100 * (ms - view.start)) / Math.max(1, view.end - view.start);
  const gapStart = gap ? Math.max(gap[0], view.start) : 0;
  const gapEnd = gap ? Math.min(gap[1], view.end) : 0;
  const presence = lanes.some(({ stream }) => stream.availability === "partial")
    ? "partial"
    : (last?.availability ?? "unavailable");
  let lastEvent: number | null = null;
  for (const { stream } of lanes) {
    if (stream.last_event_ms != null) lastEvent = stream.last_event_ms;
  }
  return (
    <section className={styles.sseTrack} data-track={source} aria-label={t(source)}>
      <div className={styles.trackHeader}>
        <strong>{t(source)}</strong>
        <div className={styles.sseStats}>
          {presence !== "captured" && <span>{t("availability." + presence)}</span>}
          {first && presence !== "empty" && (
            <span>
              {t("frameCount", { count: lanes.reduce((total, { stream }) => total + stream.frame_count, 0) })}
            </span>
          )}
          {lanes.map((lane) =>
            lane.stream.headers_ms != null ? (
              <SseHeaders
                key={lane.stream.ref}
                lane={lane}
                sessionId={sessionId}
                exchangeId={exchangeId}
                label={t("headersAt", { time: elapsed(lane.stream.headers_ms) })}
              />
            ) : null,
          )}
          {lastEvent != null && <span>{t("lastAt", { time: elapsed(lastEvent) })}</span>}
          {gap && <span className={styles.sseGapLabel}>{t("gap", { duration: elapsed(gap[1] - gap[0]) })}</span>}
          {last && <span>{t("ended", { reason: t("ending." + last.ending), time: elapsed(last.end_ms) })}</span>}
          {first && last && <span>{t("lifetime", { duration: elapsed(last.end_ms - first.started_ms) })}</span>}
        </div>
      </div>
      {first && (
        <div className={styles.ssePlot}>
          {gapEnd > gapStart && (
            <span
              className={styles.sseGap}
              style={{ left: percent(gapStart) + "%", width: percent(gapEnd) - percent(gapStart) + "%" }}
              aria-hidden="true"
            />
          )}
          {lanes.map(({ stream }) => (
            <div key={stream.ref}>
              {stream.headers_ms != null && inView(stream.headers_ms) && (
                <span
                  className={styles.headerMark}
                  title={t("headersAt", { time: elapsed(stream.headers_ms) })}
                  style={{ left: percent(stream.headers_ms) + "%" }}
                  aria-hidden="true"
                />
              )}
              {inView(stream.end_ms) && (
                <span
                  className={styles.endMark}
                  title={t("ended", { reason: t("ending." + stream.ending), time: elapsed(stream.end_ms) })}
                  data-failed={[
                    "failed",
                    "timeout",
                    "watchdog_timeout",
                    "truncated",
                    "transport_error",
                    "http_rejected",
                  ].includes(stream.ending)}
                  style={{ left: percent(stream.end_ms) + "%" }}
                  aria-hidden="true"
                />
              )}
            </div>
          ))}
          {events
            .filter(({ frame }) => inView(frame.at_ms))
            .map((event) => (
              <button
                key={event.key}
                type="button"
                tabIndex={-1}
                className={styles.sseDot}
                data-kind={event.frame.kind}
                aria-pressed={selected === event.key}
                aria-label={t("eventAt", { kind: t("kind." + event.frame.kind), time: elapsed(event.frame.at_ms) })}
                title={t("eventAt", { kind: t("kind." + event.frame.kind), time: elapsed(event.frame.at_ms) })}
                style={{ left: percent(event.frame.at_ms) + "%" }}
                onClick={() => select(event.key)}
              />
            ))}
        </div>
      )}
    </section>
  );
}

function SseHeaders({
  lane,
  sessionId,
  exchangeId,
  label,
}: {
  lane: Lane;
  sessionId: string;
  exchangeId: string;
  label: string;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const disclosureId = useId();
  const [{ open, opening }, setDisclosure] = useState({ open: false, opening: 0 });
  const stored = lane.stream.headers_available;
  const canRead = open && lane.shared && stored;
  // A disclosure must wait for its own authorization, including a rapid
  // close and reopen before RTK Query has evicted the old response.
  const query = { sessionId, exchangeId, ref: lane.stream.ref, disclosure: `${disclosureId}/${opening}` };
  const response = enhancedControlPlaneApi.useGetConversationTraceSseHeadersQuery(canRead ? query : skipToken, {
    refetchOnMountOrArgChange: true,
  });
  useRefetchOnWindowFocus(response.refetch, !canRead);
  const headers = response.isSuccess && !response.isFetching ? response.currentData?.headers : undefined;
  return (
    <details
      onToggle={(event) => {
        const open = event.currentTarget.open;
        setDisclosure((previous) => ({ open, opening: previous.opening + Number(open) }));
      }}
    >
      <summary>{label}</summary>
      {!open ? null : !stored || response.isError ? (
        <p>{t("headersUnavailable")}</p>
      ) : !lane.shared ? (
        <p>{t("headersMasked")}</p>
      ) : !headers ? (
        <p role="status">{t("loading")}</p>
      ) : Object.keys(headers).length === 0 ? (
        <p>{t("headersEmpty")}</p>
      ) : (
        <dl className={styles.httpHeaders}>
          {Object.entries(headers).map(([name, value]) => (
            <div key={name}>
              <dt>{name}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
      )}
    </details>
  );
}

function Timeline({
  lanes,
  sessionId,
  exchangeId,
}: {
  lanes: Record<TrackSource, Lane[]>;
  sessionId: string;
  exchangeId: string;
}) {
  const { t, i18n } = useTranslation(undefined, { keyPrefix: prefix });
  const [range, setRange] = useState<SseRange>();
  const [selected, setSelected] = useState<string>();
  const [focused, setFocused] = useState<string>();
  const points = {
    provider: trackFrames("provider", lanes.provider),
    outgoing: trackFrames("outgoing", lanes.outgoing),
  };
  const events = [...points.provider, ...points.outgoing].sort((a, b) => a.frame.at_ms - b.frame.at_ms);
  const end = Math.max(1, ...[...lanes.provider, ...lanes.outgoing].map(({ stream }) => stream.end_ms));
  const view = range ?? { start: 0, end };
  const visible = events.filter(({ frame }) => frame.at_ms >= view.start && frame.at_ms <= view.end);
  const active = visible.find((event) => event.key === selected) ?? visible[0];
  const focusable = visible.find((event) => event.key === focused) ?? active;
  const elapsed = traceElapsedFormatter(i18n.language);
  const kinds = new Set(events.map(({ frame }) => frame.kind));

  function selectFrame(key: string) {
    setSelected(key);
    setFocused(key);
  }

  function fit() {
    const arrivals = events.filter(({ frame }) => frame.kind !== "done" && frame.kind !== "error");
    const first = (arrivals[0] ?? events[0])?.frame.at_ms;
    const last = (arrivals[arrivals.length - 1] ?? events[events.length - 1])?.frame.at_ms;
    if (first == null || last == null) return;
    const padding = Math.max(100, Math.round((last - first) / 10));
    setRange({ start: Math.max(0, first - padding), end: Math.min(end, last + padding) });
  }

  return (
    <>
      <div className={styles.timelineCard}>
        <div className={styles.timelineToolbar}>
          <div className={styles.sseLegend}>
            {eventKinds
              .filter((kind) => kinds.has(kind))
              .map((kind) => (
                <span key={kind}>
                  <i data-kind={kind} aria-hidden="true" />
                  {t("kind." + kind)}
                </span>
              ))}
            <span>
              <i className={styles.legendGap} aria-hidden="true" />
              {t("longestGap")}
            </span>
          </div>
          <div className={styles.chips}>
            <Button type="button" size="small" variant="text" color="primary" onClick={fit} disabled={!events.length}>
              {t("fit")}
            </Button>
            <Button type="button" size="small" variant="text" color="primary" onClick={() => setRange(undefined)}>
              {t("reset")}
            </Button>
          </div>
        </div>
        <div className={styles.chartGroup}>
          {trackSources.map((source) => (
            <SseTrack
              key={source}
              source={source}
              lanes={lanes[source]}
              sessionId={sessionId}
              exchangeId={exchangeId}
              events={points[source]}
              view={view}
              selected={active?.key}
              select={selectFrame}
              elapsed={elapsed}
            />
          ))}
          <div className={styles.axis} aria-hidden="true">
            {[0, 1, 2, 3, 4].map((step) => (
              <span key={step}>{elapsed(view.start + ((view.end - view.start) * step) / 4)}</span>
            ))}
          </div>
        </div>
        <SseWindow value={view} endMs={end} onChange={setRange} elapsed={elapsed} />
      </div>
      <div className={styles.frameDetails}>
        <section aria-label={t("frameList")}>
          <h3>{t("frameList")}</h3>
          {visible.length ? (
            <ul
              className={styles.frames}
              onKeyDown={(event) => {
                if (!(event.target instanceof HTMLButtonElement)) return;
                const item = event.target.closest("li");
                const target =
                  event.key === "ArrowDown"
                    ? item?.nextElementSibling
                    : event.key === "ArrowUp"
                      ? item?.previousElementSibling
                      : event.key === "Home"
                        ? event.currentTarget.firstElementChild
                        : event.key === "End"
                          ? event.currentTarget.lastElementChild
                          : null;
                if (!target) return;
                event.preventDefault();
                target.querySelector("button")?.focus();
              }}
            >
              {visible.map((event) => (
                <li key={event.key}>
                  <button
                    type="button"
                    aria-pressed={active?.key === event.key}
                    tabIndex={focusable?.key === event.key ? 0 : -1}
                    onFocus={() => setFocused(event.key)}
                    onClick={() => selectFrame(event.key)}
                  >
                    <i data-kind={event.frame.kind} aria-hidden="true" />
                    <span>{elapsed(event.frame.at_ms)}</span>
                    <span>{t("kind." + event.frame.kind)}</span>
                    <small>{t(event.source)}</small>
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className={styles.help}>{t("noFramesInRange")}</p>
          )}
        </section>
        {active && (
          <section aria-label={t("frame")}>
            <h3>{t("frame")}</h3>
            <p className={styles.help}>
              {t(active.source)} /{" "}
              {t("eventAt", { kind: t("kind." + active.frame.kind), time: elapsed(active.frame.at_ms) })}
            </p>
            <TraceSseFramePayload
              key={active.key}
              sessionId={sessionId}
              exchangeId={exchangeId}
              refId={active.ref}
              index={active.index}
              shared={active.shared}
              stored={active.frame.offset != null}
            />
          </section>
        )}
      </div>
    </>
  );
}

export function ConversationTraceSse({
  sessionId,
  turn,
  attemptRef,
  cutoffRank,
}: {
  sessionId: string;
  turn: ConversationTraceTurn;
  attemptRef?: string;
  cutoffRank?: number;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const metadata = enhancedControlPlaneApi.useListConversationTraceSseSegmentsQuery(
    { sessionId, exchangeId: turn.exchange_id },
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  const start = (segment: TraceSseSegment) => segment.outgoing?.started_ms ?? segment.provider[0]?.started_ms ?? 0;
  const segments = [...(metadata.currentData ?? [])].sort((a, b) => start(a) - start(b));
  const canRead = (segment: TraceSseSegment) => canReadTraceArtifact(turn, cutoffRank, segment.observed_through_rank);
  const lanes = {
    provider: segments.flatMap((segment) =>
      segment.provider
        .filter((stream) => stream.ref === attemptRef)
        .map((stream) => ({ stream, shared: canRead(segment) })),
    ),
    outgoing: segments.flatMap((segment) =>
      segment.outgoing ? [{ stream: segment.outgoing, shared: canRead(segment) }] : [],
    ),
  };
  return (
    <section className={styles.sseTimeline} aria-label={t("title")}>
      <div className={styles.sectionHeading}>
        <div>
          <h2>{t("title")}</h2>
          <p>{t("description")}</p>
        </div>
      </div>
      {metadata.isError ? (
        <p role="alert">{t("unavailable")}</p>
      ) : metadata.isLoading ? (
        <p role="status">{t("loading")}</p>
      ) : !segments.length ? (
        <p>{t("unavailable")}</p>
      ) : (
        <Timeline key={attemptRef} lanes={lanes} sessionId={sessionId} exchangeId={turn.exchange_id} />
      )}
    </section>
  );
}
