// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useEffect, useLayoutEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import { parisCivilTime, startThemeCalendar } from "./themeCalendar";

export function ThemeClockPreview() {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  useLayoutEffect(() => startThemeCalendar(preview), [preview]);
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (
        event.defaultPrevented ||
        event.repeat ||
        event.isComposing ||
        event.metaKey ||
        !event.ctrlKey ||
        !event.altKey ||
        !event.shiftKey ||
        event.code !== "KeyT"
      )
        return;
      event.preventDefault();
      setDraft((value) => (value === null ? (preview ?? parisCivilTime().slice(0, 16)) : null));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [preview]);

  if (draft === null) return null;
  const valid = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(draft);
  function apply(value: string | null) {
    setPreview(value);
    setDraft(null);
  }

  return (
    <Dialog
      open
      title={t("app.themeClock.title")}
      confirmLabel={t("app.themeClock.apply")}
      confirmDisabled={!valid}
      onConfirm={() => valid && apply(draft)}
      onCancel={() => setDraft(null)}
      actionsAddon={
        <Button type="button" variant="text" size="small" color="primary" onClick={() => apply(null)}>
          {t("app.themeClock.live")}
        </Button>
      }
    >
      <label>
        {t("app.themeClock.label")}{" "}
        <input
          type="datetime-local"
          required
          min="0001-01-01T00:00"
          max="9999-12-31T23:59"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
        />
      </label>
    </Dialog>
  );
}
