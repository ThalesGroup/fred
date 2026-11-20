// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useRef } from "react";
import { useTranslation } from "react-i18next";
import styles from "./ConversationTraces.module.css";

export type SseRange = { start: number; end: number };
type Grip = "start" | "pan" | "end";

const clamp = (value: number, min: number, max: number) => Math.max(min, Math.min(max, value));

export default function SseWindow({
  value,
  endMs,
  onChange,
  elapsed,
}: {
  value: SseRange;
  endMs: number;
  onChange: (range: SseRange) => void;
  elapsed: (ms: number) => string;
}) {
  const { t } = useTranslation(undefined, { keyPrefix: "rework.admin.conversationTraces.sse" });
  const rail = useRef<HTMLDivElement>(null);
  const drag = useRef<{ grip: Grip; origin: number; range: SseRange; width: number; pointer: number } | null>(null);
  const minWindow = Math.min(100, endMs);

  function bounds(grip: Grip, range: SseRange) {
    if (grip === "start") return { min: 0, max: range.end - minWindow, current: range.start };
    if (grip === "end") return { min: range.start + minWindow, max: endMs, current: range.end };
    return { min: 0, max: endMs - (range.end - range.start), current: range.start };
  }

  function adjust(grip: Grip, range: SseRange, delta: number) {
    const { min, max, current } = bounds(grip, range);
    const next = clamp(Math.round(current + delta), min, max);
    if (grip === "start") onChange({ ...range, start: next });
    else if (grip === "end") onChange({ ...range, end: next });
    else onChange({ start: next, end: next + (range.end - range.start) });
  }

  function gripControl(grip: Grip, label: string) {
    const { min, max, current } = bounds(grip, value);
    return (
      <div
        role="slider"
        tabIndex={0}
        aria-label={label}
        aria-valuemin={min}
        aria-valuemax={max}
        aria-valuenow={current}
        aria-valuetext={
          grip === "pan"
            ? t("windowBounds", { start: elapsed(value.start), end: elapsed(value.end) })
            : elapsed(current)
        }
        className={styles.rangeGrip}
        data-grip={grip}
        onPointerDown={(event) => {
          if (event.button !== 0 || drag.current || !rail.current) return;
          event.currentTarget.focus({ preventScroll: true });
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = {
            grip,
            origin: event.clientX,
            range: value,
            width: rail.current.getBoundingClientRect().width,
            pointer: event.pointerId,
          };
        }}
        onPointerMove={(event) => {
          const active = drag.current;
          if (!active || active.pointer !== event.pointerId) return;
          adjust(active.grip, active.range, ((event.clientX - active.origin) / active.width) * endMs);
        }}
        onLostPointerCapture={(event) => {
          if (drag.current?.pointer === event.pointerId) drag.current = null;
        }}
        onKeyDown={(event) => {
          const step = Math.max(10, Math.round((value.end - value.start) / 20));
          const increments: Record<string, number> = {
            ArrowLeft: -step,
            ArrowDown: -step,
            ArrowRight: step,
            ArrowUp: step,
            Home: min - current,
            End: max - current,
          };
          const delta = increments[event.key];
          if (typeof delta !== "number") return;
          event.preventDefault();
          adjust(grip, value, delta);
        }}
      />
    );
  }

  return (
    <div className={styles.windowControl}>
      <div className={styles.rangeRail} ref={rail} role="group" aria-label={t("zoomWindow")}>
        <div
          className={styles.rangeSelection}
          style={{ left: (100 * value.start) / endMs + "%", right: (100 * (endMs - value.end)) / endMs + "%" }}
        >
          {gripControl("start", t("zoomStart"))}
          {gripControl("pan", t("zoomPan"))}
          {gripControl("end", t("zoomEnd"))}
        </div>
      </div>
      <div className={styles.rangeLegend}>
        <span>{t("windowBounds", { start: elapsed(value.start), end: elapsed(value.end) })}</span>
        <span>{t("dragWindowHelp")}</span>
      </div>
    </div>
  );
}
