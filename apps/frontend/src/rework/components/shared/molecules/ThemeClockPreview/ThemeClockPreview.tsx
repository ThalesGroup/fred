// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import type { ThemeClockSample } from "src/app/themeClock";
import styles from "./ThemeClockPreview.module.css";

const minutesPerDay = 24 * 60;
const firstDate = "0001-01-01";
const lastDate = "9999-12-31";

function clockTime(minutes: number) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
}

function shiftDate(date: string, offset: number) {
  // Step through civil dates independently of the device's time zone and DST.
  return new Date(Date.parse(date) + offset * 86_400_000).toISOString().slice(0, 10);
}

export function ThemeClockPreview() {
  const { t } = useTranslation();
  const clock = window.fredThemeClock;
  const [preview, setPreview] = useState<ThemeClockSample | null>(null);
  const [visible, setVisible] = useState(false);
  const dateInput = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLElement>(null);
  const [dragDate, setDragDate] = useState<string | null>(null);
  useLayoutEffect(() => {
    clock?.setPreview(preview);
  }, [clock, preview]);

  useEffect(() => {
    if (!clock) return;
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || event.repeat || event.isComposing || event.metaKey || !event.shiftKey) return;
      const functionKey = event.key === "F8" && !event.ctrlKey && !event.altKey;
      const originalShortcut = event.code === "KeyT" && event.ctrlKey && event.altKey;
      if (!functionKey && !originalShortcut) return;
      if (document.querySelector('[aria-modal="true"]')) return;
      event.preventDefault();
      const live = clock.getSnapshot();
      setPreview(
        (current) => current ?? { ...live, secondsSinceMidnight: Math.floor(live.secondsSinceMidnight / 60) * 60 },
      );
      setDragDate(null);
      setVisible((current) => !current);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [clock]);

  useLayoutEffect(() => {
    if (!visible) return;
    const previous = document.activeElement;
    const overlay = panel.current;
    dateInput.current?.focus({ preventScroll: true });
    return () => {
      if (
        previous instanceof HTMLElement &&
        (overlay?.contains(document.activeElement) || document.activeElement === document.body)
      ) {
        previous.focus({ preventScroll: true });
      }
    };
  }, [visible]);

  if (!visible || !preview) return null;
  const { date, secondsSinceMidnight } = preview;
  const minute = secondsSinceMidnight / 60;
  const time = clockTime(minute);
  const sliderDate = dragDate ?? date;
  const lastMinute = sliderDate === lastDate ? minutesPerDay - 1 : minutesPerDay;
  function selectDate(day: string) {
    setPreview({ date: day, secondsSinceMidnight: 0 });
  }

  function selectMinute(value: number) {
    // Anchor the whole drag so moving along the right edge cannot advance several days.
    if (value === minutesPerDay) selectDate(shiftDate(sliderDate, 1));
    else setPreview({ date: sliderDate, secondsSinceMidnight: value * 60 });
  }

  return (
    <section
      className={styles.panel}
      ref={panel}
      aria-label={t("app.themeClock.title")}
      onKeyDown={(event) => {
        if (event.key === "Escape" && !event.defaultPrevented) {
          event.stopPropagation();
          setVisible(false);
        }
      }}
    >
      <div className={styles.dateRow}>
        <IconButton
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "chevron_left" }}
          aria-label={t("app.themeClock.previous")}
          disabled={date === firstDate}
          onClick={() => selectDate(shiftDate(date, -1))}
        />
        <input
          className={styles.date}
          type="date"
          ref={dateInput}
          min={firstDate}
          max={lastDate}
          value={date}
          aria-label={t("app.themeClock.date")}
          onChange={(event) => {
            if (event.target.value && event.target.validity.valid) selectDate(event.target.value);
          }}
        />
        <IconButton
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "chevron_right" }}
          aria-label={t("app.themeClock.next")}
          disabled={date === lastDate}
          onClick={() => selectDate(shiftDate(date, 1))}
        />
        <IconButton
          variant="icon"
          size="2xs"
          icon={{ category: "outlined", type: "close" }}
          aria-label={t("common.close")}
          onClick={() => setVisible(false)}
        />
      </div>
      <div className={styles.timeRow}>
        <label htmlFor="theme-clock-slider">{t("app.themeClock.time")}</label>
        <strong>{time}</strong>
      </div>
      <input
        className={styles.slider}
        id="theme-clock-slider"
        type="range"
        min={0}
        max={lastMinute}
        step={1}
        value={dragDate && dragDate !== date ? minutesPerDay : minute}
        aria-valuetext={time}
        onPointerDown={(event) => {
          setDragDate(date);
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onLostPointerCapture={() => setDragDate(null)}
        onChange={(event) => selectMinute(event.target.valueAsNumber)}
      />
      <div className={styles.bounds} aria-hidden="true">
        <span>{clockTime(0)}</span>
        <span>{clockTime(lastMinute)}</span>
      </div>
      <Button
        variant="text"
        size="small"
        color="primary"
        onClick={() => {
          setPreview(null);
          setVisible(false);
        }}
      >
        {t("app.themeClock.live")}
      </Button>
    </section>
  );
}
