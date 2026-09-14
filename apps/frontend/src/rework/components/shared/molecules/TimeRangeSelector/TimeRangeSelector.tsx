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

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import CustomRangePanel from "./CustomRangePanel";
import MonthStrip from "./MonthStrip";
import {
  CalendarUnit,
  canShiftForward,
  getPreset,
  resolvePreset,
  shiftTimeRange,
  TIME_PRESETS,
  TimePresetKey,
  TimeRange,
} from "./timeRange.types";
import styles from "./TimeRangeSelector.module.scss";

interface TimeRangeSelectorProps {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}

const TWO_DAYS_MS = 2 * 24 * 60 * 60 * 1000;
const isMidnight = (d: Date) => d.getHours() === 0 && d.getMinutes() === 0;

/** "Aug 17 – Sep 16", with the year only once the span leaves the current year. */
function formatSpan(start: Date, end: Date, withTime: boolean, locale: string): string {
  const thisYear = new Date().getFullYear();
  const withYear = start.getFullYear() !== thisYear || end.getFullYear() !== thisYear;
  const options: Intl.DateTimeFormatOptions = {
    day: "numeric",
    month: "short",
    ...(withYear && { year: "numeric" }),
    ...(withTime && { hour: "numeric", minute: "2-digit" }),
  };
  return `${start.toLocaleString(locale, options)} – ${end.toLocaleString(locale, options)}`;
}

function formatCalendarPeriod(unit: CalendarUnit, since: Date, until: Date, locale: string): string {
  if (unit === "month") {
    const label = since.toLocaleDateString(locale, { month: "long", year: "numeric" });
    return label.charAt(0).toUpperCase() + label.slice(1);
  }
  if (unit === "day") {
    const withYear = since.getFullYear() !== new Date().getFullYear();
    return since.toLocaleDateString(locale, {
      weekday: "short",
      day: "numeric",
      month: "short",
      ...(withYear && { year: "numeric" }),
    });
  }
  // A past week's `until` is the next Monday at midnight: name the Sunday it ends on.
  return formatSpan(since, new Date(until.getTime() - 1), false, locale);
}

/** A preset reads as its name while current; once shifted, as the period it now covers. Times
 *  are shown only where they carry information: short windows and custom hours. */
function formatRangeLabel(range: TimeRange, t: (k: string) => string, locale: string): string {
  const since = new Date(range.since);
  const until = new Date(range.until);
  if (!range.presetKey) {
    return formatSpan(since, until, !(isMidnight(since) && isMidnight(until)), locale);
  }
  const { labelKey, period } = getPreset(range.presetKey);
  if (!range.offset) return t(labelKey);
  if (period.kind === "calendar") return formatCalendarPeriod(period.unit, since, until, locale);
  return formatSpan(since, until, period.durationMs < TWO_DAYS_MS, locale);
}

export default function TimeRangeSelector({ value, onChange }: TimeRangeSelectorProps) {
  const { t, i18n } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setIsOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [isOpen]);

  // Closing also on the arrows: the open dropdown's custom dates and month scroll would go stale.
  const applyAndClose = (range: TimeRange) => {
    onChange(range);
    setIsOpen(false);
  };

  const selectPreset = (key: TimePresetKey) => applyAndClose(resolvePreset(key));

  const applyCustom = (since: string, until: string) => applyAndClose({ since, until });

  const label = formatRangeLabel(value, t, i18n.language);
  const selectedMonthOffset = value.presetKey === "thisMonth" ? (value.offset ?? 0) : null;

  return (
    <div className={styles.container} ref={containerRef} data-open={isOpen}>
      <IconButton
        variant="icon"
        size="small"
        icon={{ category: "outlined", type: "chevron_left" }}
        onClick={() => applyAndClose(shiftTimeRange(value, -1))}
        title={t("rework.analytics.timeRange.previous")}
        aria-label={t("rework.analytics.timeRange.previous")}
      />
      <button
        type="button"
        className={styles.trigger}
        onClick={() => setIsOpen((prev) => !prev)}
        aria-haspopup="true"
        aria-expanded={isOpen}
        title={label}
      >
        <div className={styles.triggerInner}>
          <Icon category="outlined" type="schedule" />
          <span className={styles.label}>{label}</span>
          <Icon category="outlined" type="arrow_drop_down" />
        </div>
      </button>
      <IconButton
        variant="icon"
        size="small"
        icon={{ category: "outlined", type: "chevron_right" }}
        onClick={() => applyAndClose(shiftTimeRange(value, 1))}
        disabled={!canShiftForward(value)}
        title={t("rework.analytics.timeRange.next")}
        aria-label={t("rework.analytics.timeRange.next")}
      />

      {isOpen && (
        <div className={styles.dropdown} role="dialog">
          <div className={styles.dropdownTop}>
            <CustomRangePanel initialSince={value.since} initialUntil={value.until} onApply={applyCustom} />

            <div className={styles.divider} />

            <div className={styles.presets}>
              {TIME_PRESETS.map((preset) => (
                <button
                  key={preset.key}
                  type="button"
                  className={`${styles.presetItem} ${value.presetKey === preset.key && !value.offset ? styles.active : ""}`}
                  onClick={() => selectPreset(preset.key)}
                >
                  {t(preset.labelKey)}
                </button>
              ))}
            </div>
          </div>

          <MonthStrip
            selectedOffset={selectedMonthOffset}
            onSelect={(offset) => applyAndClose(resolvePreset("thisMonth", offset))}
          />
        </div>
      )}
    </div>
  );
}
