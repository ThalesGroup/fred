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

// Keep civil times as strings so a demo selection never picks up the browser's zone.
export function parisCivilTime(now = new Date()) {
  const parts = Object.fromEntries(eventTime.formatToParts(now).map(({ type, value }) => [type, value]));
  return `${parts.year.padStart(4, "0")}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}:${parts.second}`;
}

export function startThemeCalendar(preview: string | null = null) {
  const root = document.documentElement;
  let timer: number;
  function refresh() {
    window.clearTimeout(timer);
    const now = new Date();
    const [date, time] = (preview ?? parisCivilTime(now)).split("T");
    const [hours, minutes, seconds = 0] = time.split(":").map(Number);
    const firstDay = date.slice(0, 4) + "-01-01";
    root.dataset.calendarDate = date;
    root.dataset.calendarDayOfYear = String(1 + (Date.parse(date) - Date.parse(firstDay)) / 86_400_000);
    root.style.setProperty("--fred-seconds-since-midnight", String(hours * 3600 + minutes * 60 + seconds));
    if (preview === null && !document.hidden) timer = window.setTimeout(refresh, 60000 - (now.getTime() % 60000));
  }
  refresh();
  document.addEventListener("visibilitychange", refresh);
  window.addEventListener("pageshow", refresh);
  return () => {
    window.clearTimeout(timer);
    document.removeEventListener("visibilitychange", refresh);
    window.removeEventListener("pageshow", refresh);
    delete root.dataset.calendarDate;
    delete root.dataset.calendarDayOfYear;
    root.style.removeProperty("--fred-seconds-since-midnight");
  };
}
