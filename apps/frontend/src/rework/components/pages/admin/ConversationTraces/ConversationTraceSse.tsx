// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { skipToken } from "@reduxjs/toolkit/query";
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import Button from "@shared/atoms/Button/Button";
import { CodeBlock } from "@shared/molecules/CodeBlock/CodeBlock";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { enhancedControlPlaneApi } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type {
  ConversationTraceTurn,
  TraceSseEvent,
  TraceSseFramePage,
  TraceSseKind,
  TraceSseLane,
  TraceSseSegment,
} from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import SseWindow, { type SseRange } from "./SseWindow";
import { formatTraceJson } from "./formatTraceJson";
import {
  TRACE_TRANSLATION_PREFIX,
  TracePageButtons,
  canReadTraceArtifact,
  downloadTraceBytes,
  traceElapsedFormatter,
  traceBytes,
} from "./traceControls";
import TraceJson from "./TraceJson";
import styles from "./ConversationTraces.module.css";

type TrackSource = "provider" | "outgoing";
type Lane = { stream: TraceSseLane; shared: boolean; clip?: { start: number; until: number } };
type LanePage = TraceSseFramePage & { ref: string };
type PagedLane = { lane: Lane; source: TrackSource; pages: { index: number; startsAt: number }[] };
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
  page: LanePage | undefined,
  selectedRef?: string,
): TimedFrame[] {
  return lanes.flatMap((lane) => {
    if (selectedRef && lane.stream.ref !== selectedRef) return [];
    const lanePage = page?.ref === lane.stream.ref ? page : undefined;
    const frames = lane.stream.paged ? (lanePage?.frames ?? []) : lane.stream.frames;
    return frames.flatMap((frame, position) => {
      const index = (lanePage?.start_index ?? 0) + position;
      return withinLane(lane, frame.at_ms)
        ? [{ source, frame, ref: lane.stream.ref, index, shared: lane.shared, key: lane.stream.ref + "-" + index }]
        : [];
    });
  });
}

function selectablePages(lane: Lane): PagedLane["pages"] {
  const starts = lane.stream.page_starts_ms ?? [];
  const clip = lane.clip;
  return lane.stream.paged
    ? starts.flatMap((startsAt, index) =>
        !clip || (startsAt < clip.until && (starts[index + 1] ?? Infinity) >= clip.start) ? [{ index, startsAt }] : [],
      )
    : [];
}

function otherPageInRange({ lane, pages }: PagedLane, range: SseRange, currentPage: number) {
  const start = Math.max(range.start, lane.clip?.start ?? 0);
  const end = Math.min(range.end, lane.clip?.until ?? Infinity, lane.stream.last_event_ms ?? lane.stream.end_ms);
  if (end < start) return -1;
  const startsInRange = pages.findIndex(
    ({ startsAt }, index) => index !== currentPage && start <= startsAt && startsAt <= end,
  );
  if (startsInRange >= 0) return startsInRange;
  return pages.findIndex(({ startsAt }, index) => {
    const nextAt = pages[index + 1]?.startsAt ?? end;
    return index !== currentPage && startsAt <= end && nextAt >= start;
  });
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
  const [pageChoice, setPageChoice] = useState<{ ref: string; page?: number }>();
  const frameList = useRef<HTMLUListElement>(null);
  const navigationHelpId = useId();
  const hasDurableEvents = trackSources.some((source) =>
    lanes[source].some(({ stream }) => stream.paged && stream.page_starts_ms?.length),
  );
  const pagedLanes = hasDurableEvents
    ? trackSources.flatMap((source) =>
        lanes[source].flatMap((lane) => {
          const pages = selectablePages(lane);
          return pages.length || (!lane.stream.paged && lane.stream.frames.length) ? [{ lane, source, pages }] : [];
        }),
      )
    : [];
  const pagedLane =
    pagedLanes.find(({ lane }) => lane.stream.ref === pageChoice?.ref) ??
    pagedLanes.find(({ lane }) => failureEndings.has(lane.stream.ending)) ??
    pagedLanes[0];
  const laneRef = pagedLane?.lane.stream.ref;
  const pageCount = pagedLane?.pages.length ?? 0;
  const defaultPage = pagedLane && failureEndings.has(pagedLane.lane.stream.ending) ? pageCount - 1 : 0;
  const chosenPage = laneRef === pageChoice?.ref ? pageChoice?.page : undefined;
  const page = Math.max(0, Math.min(chosenPage ?? defaultPage, pageCount - 1));
  const lanePage = pagedLane?.pages[page];
  const pageArgs =
    laneRef && lanePage && pagedLane?.lane.shared
      ? { sessionId, exchangeId, ref: laneRef, page: lanePage.index }
      : skipToken;
  const frameQuery = enhancedControlPlaneApi.useGetConversationTraceSseFramePageQuery(pageArgs, {
    refetchOnMountOrArgChange: true,
  });
  useRefetchOnWindowFocus(frameQuery.refetch, pageArgs === skipToken);
  const framePage =
    laneRef && pagedLane?.lane.shared && !frameQuery.isFetching && !frameQuery.isError && frameQuery.currentData
      ? { ...frameQuery.currentData, ref: laneRef }
      : undefined;
  const points = {
    provider: trackFrames("provider", lanes.provider, framePage, laneRef),
    outgoing: trackFrames("outgoing", lanes.outgoing, framePage, laneRef),
  };
  const events = [...points.provider, ...points.outgoing].sort((a, b) => a.frame.at_ms - b.frame.at_ms);
  const end = Math.max(
    1,
    ...[...lanes.provider, ...lanes.outgoing].map(({ stream, clip }) =>
      Math.min(stream.end_ms, clip?.until ?? Infinity),
    ),
  );
  const view = range ?? { start: 0, end };
  const visible = events.filter(({ frame }) => frame.at_ms >= view.start && frame.at_ms <= view.end);
  const rangePage = range && pagedLane?.lane.shared && !visible.length ? otherPageInRange(pagedLane, range, page) : -1;
  const framesNotRetained =
    events.length === 0 &&
    !pagedLane &&
    [...lanes.provider, ...lanes.outgoing].some(({ clip, stream }) => {
      if (clip || !stream.frame_count) return false;
      return stream.paged ? !stream.page_starts_ms?.length : !stream.frames.length;
    });
  const active = visible.find((event) => event.key === selected) ?? visible[0];
  const elapsed = traceElapsedFormatter(i18n.language);
  const kinds = new Set(events.map(({ frame }) => frame.kind));

  function selectPage(ref: string, page?: number, zoom?: SseRange) {
    setPageChoice({ ref, page });
    setRange(zoom);
    setSelected(undefined);
  }

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
          {pagedLane && (
            <p className={styles.help}>
              {t("pageStream", { stream: t(pagedLane.source), time: elapsed(pagedLane.lane.stream.started_ms) })}
            </p>
          )}
          {pagedLanes.length > 1 && (
            <label className={styles.tracePageField}>
              {t("eventStream")}
              <select value={laneRef} onChange={(event) => selectPage(event.target.value)}>
                {pagedLanes.map(({ lane, source }) => (
                  <option key={lane.stream.ref} value={lane.stream.ref}>
                    {t("streamStarted", { stream: t(source), time: elapsed(lane.stream.started_ms) })}
                  </option>
                ))}
              </select>
            </label>
          )}
          {laneRef && pagedLane?.lane.shared && pageCount > 1 && (
            <form
              className={styles.tracePageField}
              onSubmit={(event) => {
                event.preventDefault();
                const target = Number(new FormData(event.currentTarget).get("page"));
                if (Number.isInteger(target) && target >= 1 && target <= pageCount) selectPage(laneRef, target - 1);
              }}
            >
              <label>
                {t("pageOf", { count: pageCount })}
                <input
                  key={laneRef + page}
                  type="number"
                  name="page"
                  min={1}
                  max={pageCount}
                  defaultValue={page + 1}
                  required
                />
              </label>
              <Button type="submit" size="small" variant="outlined" color="secondary">
                {t("openPage")}
              </Button>
            </form>
          )}
          {laneRef && pagedLane?.lane.shared && (
            <TracePageButtons
              label={t("framePages")}
              pager={{
                cursor: page > 0 ? String(page) : undefined,
                previous: () => selectPage(laneRef, page - 1),
                next: (cursor) => selectPage(laneRef, Number(cursor)),
              }}
              nextCursor={page < pageCount - 1 ? String(page + 1) : null}
              disabled={frameQuery.isFetching}
            />
          )}
          {lanePage && pagedLane?.lane.shared && (
            <p className={styles.help}>{t("pageStartsAt", { time: elapsed(lanePage.startsAt) })}</p>
          )}
          {visible.length > 1 && (
            <p id={navigationHelpId} className={styles.help}>
              {t("frameNavigation")}
            </p>
          )}
          {visible.length ? (
            <ul
              className={styles.frames}
              ref={frameList}
              aria-describedby={visible.length > 1 ? navigationHelpId : undefined}
              onKeyDown={(event) => {
                if (!active || !(event.target instanceof HTMLButtonElement)) return;
                const sameLane = event.key === "ArrowLeft" || event.key === "ArrowRight";
                const sequence = sameLane ? visible.filter(({ source }) => source === active.source) : visible;
                const index = sequence.indexOf(active);
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
                    tabIndex={active?.key === event.key ? 0 : -1}
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
          ) : laneRef && rangePage >= 0 && !frameQuery.isFetching ? (
            <Button
              type="button"
              size="small"
              variant="outlined"
              color="secondary"
              onClick={() => selectPage(laneRef, rangePage, range)}
            >
              {t("loadEventsInRange")}
            </Button>
          ) : (
            <p className={styles.help} role={frameQuery.isFetching ? "status" : undefined}>
              {t(
                pagedLane?.lane.stream.paged && !pagedLane.lane.shared
                  ? "maskedFrameIndex"
                  : frameQuery.isFetching
                    ? "loading"
                    : frameQuery.isError
                      ? "frameIndexUnavailable"
                      : framesNotRetained
                        ? "framesNotRetained"
                        : "noFramesInRange",
              )}
            </p>
          )}
        </section>
        {active && (
          <section className={styles.framePayload} aria-label={t("frame")}>
            <h3>{t("frame")}</h3>
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
    { refetchOnMountOrArgChange: true, refetchOnFocus: true },
  );
  const previousStatus = useRef(turn.capture_status);
  const { capture_status: status } = turn;
  const { refetch } = metadata;
  useEffect(() => {
    const wasSaving = previousStatus.current === "saving";
    previousStatus.current = status;
    if (wasSaving && status !== "saving" && attemptRef !== null) void refetch();
  }, [attemptRef, refetch, status]);
  const start = (segment: TraceSseSegment) => segment.outgoing?.started_ms ?? segment.provider[0]?.started_ms ?? 0;
  const segments = [...(metadata.currentData ?? [])].sort((a, b) => start(a) - start(b));
  const canRead = (segment: TraceSseSegment) => canReadTraceArtifact(turn, cutoffRank, segment.observed_through_rank);
  const lanes: Record<TrackSource, Lane[]> = { provider: [], outgoing: [] };
  for (const segment of segments) {
    const shared = canRead(segment);
    const attempt = segment.provider.find((stream) => stream.ref === attemptRef);
    if (attemptRef && !attempt) continue;
    lanes.provider.push(...(attempt ? [attempt] : segment.provider).map((stream) => ({ stream, shared })));
    if (segment.outgoing) {
      const clip = attempt ? outgoingClip(attempt, segment.provider) : undefined;
      if (!attempt || (clip && clip.start <= segment.outgoing.end_ms)) {
        lanes.outgoing.push({ stream: segment.outgoing, shared, clip });
      }
    }
  }
  const paged = trackSources.some((source) => lanes[source].some(({ stream }) => stream.paged));
  return (
    <section className={styles.sseTimeline} aria-label={t("title")}>
      <div className={styles.sectionHeading}>
        <div>
          <h2>{t("title")}</h2>
          <p>{t(paged ? "pagedDescription" : "description")}</p>
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
