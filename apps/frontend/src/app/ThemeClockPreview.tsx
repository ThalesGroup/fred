// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { parisCivilTime, startThemeCalendar } from "./themeCalendar";
import styles from "./ThemeClockPreview.module.css";

const firstMinute = 8 * 60;
const lastMinute = 20 * 60;
const firstDate = "0001-01-01";
const lastDate = "9999-12-31";

function clockTime(minutes: number) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${pad(Math.floor(minutes / 60))}:${pad(minutes % 60)}`;
}

function initialPreview() {
  const [date, time] = parisCivilTime().split("T");
  const minuteTime = time.slice(0, 5);
  const start = clockTime(firstMinute);
  const end = clockTime(lastMinute);
  return date + "T" + (minuteTime < start ? start : minuteTime > end ? end : minuteTime);
}

export function ThemeClockPreview() {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<string | null>(null);
  const [visible, setVisible] = useState(false);
  const dateInput = useRef<HTMLInputElement>(null);
  const panel = useRef<HTMLElement>(null);
  useLayoutEffect(() => startThemeCalendar(preview), [preview]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.defaultPrevented || event.repeat || event.isComposing || event.metaKey || !event.shiftKey) return;
      const functionKey = event.key === "F8" && !event.ctrlKey && !event.altKey;
      const originalShortcut = event.code === "KeyT" && event.ctrlKey && event.altKey;
      if (!functionKey && !originalShortcut) return;
      event.preventDefault();
      setPreview((current) => current ?? initialPreview());
      setVisible((current) => !current);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
  const [date, time] = preview.split("T");
  const [hour, minute] = time.split(":").map(Number);
  function stepDay(offset: number) {
    // Work in civil days so a DST transition or the browser's time zone cannot skip a date.
    const nextDay = new Date(Date.parse(date) + offset * 86_400_000);
    setPreview(nextDay.toISOString().slice(0, 10) + "T" + time);
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
          onClick={() => stepDay(-1)}
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
            if (event.target.value && event.target.validity.valid) setPreview(event.target.value + "T" + time);
          }}
        />
        <IconButton
          variant="icon"
          size="small"
          icon={{ category: "outlined", type: "chevron_right" }}
          aria-label={t("app.themeClock.next")}
          disabled={date === lastDate}
          onClick={() => stepDay(1)}
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
        min={firstMinute}
        max={lastMinute}
        step={1}
        value={hour * 60 + minute}
        aria-valuetext={time}
        onChange={(event) => setPreview(date + "T" + clockTime(event.target.valueAsNumber))}
      />
      <div className={styles.bounds} aria-hidden="true">
        <span>{clockTime(firstMinute)}</span>
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
