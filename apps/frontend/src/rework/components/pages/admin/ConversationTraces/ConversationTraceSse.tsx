// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { skipToken } from "@reduxjs/toolkit/query";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import Button from "@shared/atoms/Button/Button";
import { CodeBlock } from "@shared/molecules/CodeBlock/CodeBlock";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ConversationTraceTurn,
  TraceSseEvent,
  TraceSseFramePage,
  TraceSseKind,
  TraceSseLane,
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
import { type SsePageRequest, useSseFramePages } from "./useSseFramePages";

type TrackSource = "provider" | "outgoing";
type Lane = { stream: TraceSseLane; shared: boolean; clip?: { start: number; until: number } };
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
const failureEndings = new Set<TraceSseLane["ending"]>([
  "failed",
  "timeout",
  "watchdog_timeout",
  "truncated",
  "transport_error",
  "http_rejected",
]);

function withinLane({ clip }: Lane, ms: number) {
  return !clip || (ms >= clip.start && ms < clip.until);
}

function outgoingClip(attempt: TraceSseLane, otherAttempts: TraceSseLane[]) {
  // Outgoing frames share the segment clock but have no call ID. Keep the
  // interval between requests, excluding time when an earlier request overlaps.
  let start = attempt.started_ms;
  let until = Infinity;
  for (const other of otherAttempts) {
    if (other.ref === attempt.ref) continue;
    if (other.started_ms > attempt.started_ms) {
      until = Math.min(until, other.started_ms);
    } else if (other.end_ms >= attempt.started_ms) {
      start = Math.max(start, other.end_ms + 1);
    }
  }
  return start < until && start <= attempt.end_ms ? { start, until } : undefined;
}

function trackFrames(
  source: TrackSource,
  lanes: Lane[],
  pages: Map<string, TraceSseFramePage[]> | undefined,
): TimedFrame[] {
  return lanes.flatMap((lane) => {
    const { ref } = lane.stream;
    const withOrdinals = (items: TraceSseEvent[], start: number) =>
      items.flatMap((frame, position) => {
        const index = start + position;
        return withinLane(lane, frame.at_ms)
          ? [{ source, frame, ref, index, shared: lane.shared, key: ref + "-" + index }]
          : [];
      });
    return (pages?.get(ref) ?? []).flatMap((page) => withOrdinals(page.frames, page.start_index));
  });
}

function pagesInLane({ stream, clip }: Lane) {
  const starts = stream.page_starts_ms ?? [];
  return starts.flatMap((start, page) =>
    !clip || (start < clip.until && (starts[page + 1] ?? Infinity) >= clip.start) ? [page] : [],
  );
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
  const gap = lanes.reduce<[number, number] | undefined>((largest, lane) => {
    const candidate = lane.stream.longest_gap;
    return candidate &&
      withinLane(lane, candidate[0]) &&
      withinLane(lane, candidate[1]) &&
      (!largest || candidate[1] - candidate[0] > largest[1] - largest[0])
      ? candidate
      : largest;
  }, undefined);
  const first = lanes[0];
  const last = lanes[lanes.length - 1];
  const inView = (ms: number) => ms >= view.start && ms <= view.end;
  const percent = (ms: number) => (100 * (ms - view.start)) / Math.max(1, view.end - view.start);
  const gapStart = gap ? Math.max(gap[0], view.start) : 0;
  const gapEnd = gap ? Math.min(gap[1], view.end) : 0;
  const presence = lanes.some(({ stream }) => stream.availability === "partial")
    ? "partial"
    : (last?.stream.availability ?? "unavailable");
  let lastEvent: number | null = null;
  for (const lane of lanes) {
    const { last_event_ms } = lane.stream;
    if (last_event_ms != null && withinLane(lane, last_event_ms)) lastEvent = last_event_ms;
  }
  lastEvent = lastEvent ?? events[events.length - 1]?.frame.at_ms ?? null;
  const terminal = last && withinLane(last, last.stream.end_ms) ? last.stream : undefined;
  return (
    <section className={styles.sseTrack} data-track={source} aria-label={t(source)}>
      <div className={styles.trackHeader}>
        <strong>{t(source)}</strong>
        <div className={styles.sseStats}>
          {presence !== "captured" && <span>{t("availability." + presence)}</span>}
          {first && presence !== "empty" && (
            <span>
              {first.clip
                ? t("markerCount", { count: events.length })
                : t("frameCount", { count: lanes.reduce((total, { stream }) => total + stream.frame_count, 0) })}
            </span>
          )}
          {lanes.map((lane) =>
            lane.stream.headers_ms != null && withinLane(lane, lane.stream.headers_ms) ? (
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
          {terminal && (
            <span>{t("ended", { reason: t("ending." + terminal.ending), time: elapsed(terminal.end_ms) })}</span>
          )}
          {first && !first.clip && terminal && (
            <span>{t("lifetime", { duration: elapsed(terminal.end_ms - first.stream.started_ms) })}</span>
          )}
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
          {lanes.map((lane) => {
            const { stream } = lane;
            return (
              <div key={stream.ref}>
                {stream.headers_ms != null && withinLane(lane, stream.headers_ms) && inView(stream.headers_ms) && (
                  <span
                    className={styles.headerMark}
                    title={t("headersAt", { time: elapsed(stream.headers_ms) })}
                    style={{ left: percent(stream.headers_ms) + "%" }}
                    aria-hidden="true"
                  />
                )}
                {withinLane(lane, stream.end_ms) && inView(stream.end_ms) && (
                  <span
                    className={styles.endMark}
                    title={t("ended", { reason: t("ending." + stream.ending), time: elapsed(stream.end_ms) })}
                    data-failed={failureEndings.has(stream.ending)}
                    style={{ left: percent(stream.end_ms) + "%" }}
                    aria-hidden="true"
                  />
                )}
              </div>
            );
          })}
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
  const frameList = useRef<HTMLUListElement>(null);
  const navigationHelpId = useId();
  const allLanes = useMemo(() => [...lanes.provider, ...lanes.outgoing], [lanes]);
  const pageRequests = useMemo<SsePageRequest[]>(
    () =>
      allLanes.flatMap((lane) =>
        lane.shared ? pagesInLane(lane).map((page) => ({ sessionId, exchangeId, ref: lane.stream.ref, page })) : [],
      ),
    [allLanes, sessionId, exchangeId],
  );
  const indexes = useSseFramePages(pageRequests);
  const points = useMemo(
    () => ({
      provider: trackFrames("provider", lanes.provider, indexes.pages),
      outgoing: trackFrames("outgoing", lanes.outgoing, indexes.pages),
    }),
    [lanes, indexes.pages],
  );
  const events = useMemo(
    () => [...points.provider, ...points.outgoing].sort((a, b) => a.frame.at_ms - b.frame.at_ms),
    [points],
  );
  const end = Math.max(1, ...allLanes.map(({ stream, clip }) => Math.min(stream.end_ms, clip?.until ?? Infinity)));
  const view = range ?? { start: 0, end };
  const visible = events.filter(({ frame }) => frame.at_ms >= view.start && frame.at_ms <= view.end);
  const hasMaskedIndex = allLanes.some((lane) => !lane.shared && pagesInLane(lane).length);
  const framesNotRetained =
    events.length === 0 &&
    allLanes.some(({ clip, stream }) => !clip && stream.frame_count > 0 && !stream.page_starts_ms?.length);
  const active = visible.find((event) => event.key === selected);
  const focusable = active ?? visible[0];
  const elapsed = traceElapsedFormatter(i18n.language);
  const kinds = new Set(events.map(({ frame }) => frame.kind));

  function selectFrame(key: string) {
    setSelected(key);
    const list = frameList.current;
    const button = list?.children[visible.findIndex((event) => event.key === key)]?.querySelector("button");
    if (!list || !button) return;
    button.focus({ preventScroll: true });
    list.scrollTop +=
      button.getBoundingClientRect().top -
      list.getBoundingClientRect().top -
      (list.clientHeight - button.offsetHeight) / 2;
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
          {indexes.isLoading && <p role="status">{t("loading")}</p>}
          {indexes.hasError && <p role="status">{t("frameIndexUnavailable")}</p>}
          {hasMaskedIndex && <p className={styles.help}>{t("maskedFrameIndex")}</p>}
          {visible.length > 1 && (
            <p id={navigationHelpId} className={styles.help}>
              {t("frameNavigation")}
            </p>
          )}
          {visible.length > 0 && (
            <ul
              className={styles.frames}
              ref={frameList}
              aria-describedby={visible.length > 1 ? navigationHelpId : undefined}
              onKeyDown={(event) => {
                if (!focusable || !(event.target instanceof HTMLButtonElement)) return;
                const sameLane = event.key === "ArrowLeft" || event.key === "ArrowRight";
                const sequence = sameLane ? visible.filter(({ source }) => source === focusable.source) : visible;
                const index = sequence.indexOf(focusable);
                let target: TimedFrame | undefined;
                switch (event.key) {
                  case "ArrowLeft":
                  case "ArrowUp":
                    target = sequence[index - 1];
                    break;
                  case "ArrowRight":
                  case "ArrowDown":
                    target = sequence[index + 1];
                    break;
                  case "Home":
                    target = sequence[0];
                    break;
                  case "End":
                    target = sequence[sequence.length - 1];
                    break;
                  default:
                    return;
                }
                event.preventDefault();
                if (target) selectFrame(target.key);
              }}
            >
              {visible.map((event) => (
                <li key={event.key}>
                  <button
                    type="button"
                    aria-pressed={active?.key === event.key}
                    tabIndex={focusable?.key === event.key ? 0 : -1}
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
          )}
          {!visible.length && !indexes.isLoading && !indexes.hasError && !hasMaskedIndex && (
            <p className={styles.help}>{t(framesNotRetained ? "framesNotRetained" : "noFramesInRange")}</p>
          )}
        </section>
        {visible.length > 0 && (
          <section className={styles.framePayload} aria-label={t("frame")}>
            <h3>{t("frame")}</h3>
            {active ? (
              <>
                <p className={styles.help}>
                  {t(active.source)} /{" "}
                  {t("eventAt", { kind: t("kind." + active.frame.kind), time: elapsed(active.frame.at_ms) })}
                </p>
                <div key={active.key} className={styles.framePayloadBody}>
                  <TraceSseFramePayload
                    sessionId={sessionId}
                    exchangeId={exchangeId}
                    refId={active.ref}
                    index={active.index}
                    shared={active.shared}
                    stored={active.frame.offset != null}
                  />
                </div>
              </>
            ) : (
              <p className={styles.help}>{t("chooseEvent")}</p>
            )}
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
  attemptRef?: string | null;
  cutoffRank?: number;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: prefix });
  const metadata = enhancedControlPlaneApi.useListConversationTraceSseSegmentsQuery(
    attemptRef === null ? skipToken : { sessionId, exchangeId: turn.exchange_id },
    { refetchOnMountOrArgChange: true },
  );
  const previousStatus = useRef(turn.capture_status);
  const { capture_status: status } = turn;
  const { refetch } = metadata;
  useEffect(() => {
    const wasSaving = previousStatus.current === "saving";
    previousStatus.current = status;
    if (wasSaving && status !== "saving" && attemptRef !== null) void refetch();
  }, [attemptRef, refetch, status]);
  const lanes = useMemo(() => {
    const result: Record<TrackSource, Lane[]> = { provider: [], outgoing: [] };
    for (const segment of metadata.currentData ?? []) {
      const shared = canReadTraceArtifact(turn, cutoffRank, segment.observed_through_rank);
      const attempt = segment.provider.find((stream) => stream.ref === attemptRef);
      if (attemptRef && !attempt) continue;
      result.provider.push(...(attempt ? [attempt] : segment.provider).map((stream) => ({ stream, shared })));
      if (segment.outgoing) {
        const clip = attempt ? outgoingClip(attempt, segment.provider) : undefined;
        if (!attempt || (clip && clip.start <= segment.outgoing.end_ms)) {
          result.outgoing.push({ stream: segment.outgoing, shared, clip });
        }
      }
    }
    for (const source of trackSources) {
      result[source].sort((a, b) => a.stream.started_ms - b.stream.started_ms);
    }
    return result;
  }, [metadata.currentData, turn, cutoffRank, attemptRef]);
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
      ) : !lanes.provider.length && !lanes.outgoing.length ? (
        <p>{t("unavailable")}</p>
      ) : (
        <Timeline
          key={attemptRef ?? turn.exchange_id}
          lanes={lanes}
          sessionId={sessionId}
          exchangeId={turn.exchange_id}
        />
      )}
    </section>
  );
}
