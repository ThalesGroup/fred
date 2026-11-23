// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

const eventTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "Europe/Paris",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hourCycle: "h23",
});

export function startThemeCalendar() {
  const root = document.documentElement;
  let timer: number;
  function refresh() {
    window.clearTimeout(timer);
    const now = new Date();
    const parts = Object.fromEntries(eventTime.formatToParts(now).map(({ type, value }) => [type, value]));
    root.dataset.calendarDate = `${parts.year}-${parts.month}-${parts.day}`;
    const seconds = Number(parts.hour) * 3600 + Number(parts.minute) * 60 + Number(parts.second);
    root.style.setProperty("--fred-seconds-since-midnight", String(seconds));
    if (!document.hidden) timer = window.setTimeout(refresh, 60000 - (now.getTime() % 60000));
  }
  refresh();
  document.addEventListener("visibilitychange", refresh);
  window.addEventListener("pageshow", refresh);
  return () => {
    window.clearTimeout(timer);
    document.removeEventListener("visibilitychange", refresh);
    window.removeEventListener("pageshow", refresh);
    delete root.dataset.calendarDate;
    root.style.removeProperty("--fred-seconds-since-midnight");
  };
}
