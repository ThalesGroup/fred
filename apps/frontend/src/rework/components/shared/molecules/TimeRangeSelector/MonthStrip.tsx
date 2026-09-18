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

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { startOfUnit } from "./timeRange.types";
import styles from "./TimeRangeSelector.module.scss";

interface MonthStripProps {
  /** Month offset of the selected range (0 = current month), or null when the range is not a month. */
  selectedOffset: number | null;
  onSelect: (offset: number) => void;
}

const INITIAL_MONTHS = 24;
// Older months kept left of a selected past month, so it can be centred when the dropdown opens.
const MONTHS_BEFORE_SELECTED = 6;
const LOAD_STEP = 12;
const LOAD_THRESHOLD_PX = 48;

interface Month {
  offset: number;
  date: Date;
}

/** Months from `count - 1` ago up to the current one, grouped by year, oldest first. */
function monthsByYear(count: number): { year: number; months: Month[] }[] {
  const now = new Date();
  const years: { year: number; months: Month[] }[] = [];
  for (let offset = -(count - 1); offset <= 0; offset++) {
    const date = startOfUnit("month", now, offset);
    const last = years[years.length - 1];
    if (last?.year === date.getFullYear()) last.months.push({ offset, date });
    else years.push({ year: date.getFullYear(), months: [{ offset, date }] });
  }
  return years;
}

/** Month timeline: current month on the right, older ones loaded as the user scrolls left. */
export default function MonthStrip({ selectedOffset, onSelect }: MonthStripProps) {
  const { t, i18n } = useTranslation();
  const [count, setCount] = useState(() =>
    Math.max(INITIAL_MONTHS, 1 + MONTHS_BEFORE_SELECTED - (selectedOffset ?? 0)),
  );
  const scrollerRef = useRef<HTMLDivElement>(null);
  // Width before older months were prepended, so the view can be pushed back by what was added.
  const widthBeforeLoad = useRef<number | null>(null);
  const years = useMemo(() => monthsByYear(count), [count]);

  useLayoutEffect(() => {
    const el = scrollerRef.current!;
    const selected = el.querySelector<HTMLElement>('[aria-pressed="true"]');
    el.scrollLeft = selected ? selected.offsetLeft - (el.clientWidth - selected.offsetWidth) / 2 : el.scrollWidth;
  }, []);

  useLayoutEffect(() => {
    const el = scrollerRef.current!;
    if (widthBeforeLoad.current === null) return;
    el.scrollLeft += el.scrollWidth - widthBeforeLoad.current;
    widthBeforeLoad.current = null;
  }, [count]);

  // A plain mouse wheel only scrolls vertically; turn it into horizontal travel along the timeline.
  // Non-passive so the page behind the dropdown does not scroll along.
  useEffect(() => {
    const el = scrollerRef.current!;
    const onWheel = (e: WheelEvent) => {
      if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
      e.preventDefault();
      el.scrollLeft += e.deltaY;
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const handleScroll = () => {
    const el = scrollerRef.current!;
    if (el.scrollLeft > LOAD_THRESHOLD_PX || widthBeforeLoad.current !== null) return;
    widthBeforeLoad.current = el.scrollWidth;
    setCount((c) => c + LOAD_STEP);
  };

  const monthLabel = (date: Date, month: "short" | "long") =>
    date.toLocaleDateString(i18n.language, month === "short" ? { month } : { month, year: "numeric" });

  return (
    <div
      ref={scrollerRef}
      className={styles.monthStrip}
      onScroll={handleScroll}
      role="group"
      aria-label={t("rework.analytics.timeRange.months")}
    >
      {years.map(({ year, months }) => (
        <div key={year} className={styles.yearGroup}>
          <span className={styles.yearLabel}>{year}</span>
          <div className={styles.yearMonths}>
            {months.map(({ offset, date }) => (
              <button
                key={offset}
                type="button"
                className={`${styles.presetItem} ${styles.monthItem} ${offset === selectedOffset ? styles.active : ""}`}
                aria-pressed={offset === selectedOffset}
                aria-label={monthLabel(date, "long")}
                onClick={() => onSelect(offset)}
              >
                {monthLabel(date, "short")}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
