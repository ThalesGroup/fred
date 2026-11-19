// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { skipToken } from "@reduxjs/toolkit/query";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import Button from "@shared/atoms/Button/Button";
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
import { TRACE_TRANSLATION_PREFIX, canReadTraceArtifact, downloadTraceBytes, traceBytes } from "./traceControls";
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
  if (!response.currentData) return <p role="status">{t("loading")}</p>;

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
        <pre className={styles.httpText} tabIndex={0} aria-label={t("frame")}>
          {raw}
        </pre>
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
      <strong>{t(source)}</strong>
      <div className={styles.sseStats}>
        <span>{t("availability." + presence)}</span>
        {first && (
          <span>{t("frameCount", { count: lanes.reduce((total, { stream }) => total + stream.frame_count, 0) })}</span>
        )}
        {lastEvent != null && <span>{t("lastAt", { time: elapsed(lastEvent) })}</span>}
        {gap && <span className={styles.sseGapLabel}>{t("gap", { duration: elapsed(gap[1] - gap[0]) })}</span>}
        {last && <span>{t("ended", { reason: t("ending." + last.ending), time: elapsed(last.end_ms) })}</span>}
        {first && last && <span>{t("lifetime", { duration: elapsed(last.end_ms - first.started_ms) })}</span>}
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
                  className={styles.sseBoundary}
                  style={{ left: percent(stream.headers_ms) + "%" }}
                  aria-hidden="true"
                />
              )}
              {inView(stream.end_ms) && (
                <span
                  className={styles.sseBoundary}
                  data-end
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
        <dl>
          {Object.entries(headers).map(([name, value]) => (
            <div key={name} className={styles.httpHeader}>
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
  const points = {
    provider: trackFrames("provider", lanes.provider),
    outgoing: trackFrames("outgoing", lanes.outgoing),
  };
  const events = [...points.provider, ...points.outgoing].sort((a, b) => a.frame.at_ms - b.frame.at_ms);
  const end = Math.max(1, ...[...lanes.provider, ...lanes.outgoing].map(({ stream }) => stream.end_ms));
  const view = range ?? { start: 0, end };
  const visible = events.filter(({ frame }) => frame.at_ms >= view.start && frame.at_ms <= view.end);
  const active = visible.find((event) => event.key === selected);
  const seconds = new Intl.NumberFormat(i18n.language, { style: "unit", unit: "second", maximumFractionDigits: 3 });
  const milliseconds = new Intl.NumberFormat(i18n.language, { style: "unit", unit: "millisecond" });
  const elapsed = (ms: number) => (ms >= 1000 ? seconds.format(ms / 1000) : milliseconds.format(ms));
  const kinds = new Set(events.map(({ frame }) => frame.kind));

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
      <header className={styles.sseControls}>
        <span>{t("turnElapsed", { duration: elapsed(end) })}</span>
        <div className={styles.sseControls}>
          <Button type="button" size="2xs" variant="text" color="on-surface" onClick={fit} disabled={!events.length}>
            {t("fit")}
          </Button>
          <Button type="button" size="2xs" variant="text" color="on-surface" onClick={() => setRange(undefined)}>
            {t("reset")}
          </Button>
        </div>
      </header>
      {trackSources.map((source) => (
        <SseTrack
          key={source}
          source={source}
          lanes={lanes[source]}
          sessionId={sessionId}
          exchangeId={exchangeId}
          events={points[source]}
          view={view}
          selected={selected}
          select={setSelected}
          elapsed={elapsed}
        />
      ))}
      <div className={styles.sseLegend}>
        {eventKinds
          .filter((kind) => kinds.has(kind))
          .map((kind) => (
            <span key={kind}>
              <i data-kind={kind} aria-hidden="true" />
              {t("kind." + kind)}
            </span>
          ))}
      </div>
      <SseWindow value={view} endMs={end} onChange={setRange} elapsed={elapsed} />
      {visible.length > 0 && (
        <label className={styles.sseEventSelect}>
          {t("event")}
          <select value={active?.key ?? ""} onChange={(event) => setSelected(event.target.value)}>
            <option value="">{t("chooseEvent")}</option>
            {visible.map((event) => (
              <option key={event.key} value={event.key}>
                {t(event.source)} /{" "}
                {t("eventAt", { kind: t("kind." + event.frame.kind), time: elapsed(event.frame.at_ms) })}
              </option>
            ))}
          </select>
        </label>
      )}
      {active && (
        <TraceSseFramePayload
          key={active.key}
          sessionId={sessionId}
          exchangeId={exchangeId}
          refId={active.ref}
          index={active.index}
          shared={active.shared}
          stored={active.frame.offset != null}
        />
      )}
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
      <h4>{t("title")}</h4>
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
