// Copyright Thales 2025
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

// ---------------------------------------------------------------------------
// KEA MIGRATION (one-shot, throwaway-on-kea).
// Announces, once per session (i.e. once per login), that the new version is
// available. Color, texts and links come from the platform-managed
// frontend_settings.properties.migrationBanner; without it, nothing renders.
// Rendered as an overlay over the page content only — never over the sidebar.
// ---------------------------------------------------------------------------

import { Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import styles from "./MigrationBanner.module.css";

const DISMISSED_KEY = "kea-migration-banner-dismissed";
const AUTO_HIDE_MS = 30_000;

const wasDismissed = () => {
  try {
    return sessionStorage.getItem(DISMISSED_KEY) === "true";
  } catch {
    return false; // private mode / storage disabled: show the banner anyway
  }
};

const markDismissed = () => {
  try {
    sessionStorage.setItem(DISMISSED_KEY, "true");
  } catch {
    /* storage unavailable — the banner simply reappears on reload */
  }
};

const resolveLocalized = (map: { [key: string]: string } | undefined | null, lang: string): string | null =>
  map ? (map[lang] ?? map["en"] ?? null) : null;

export default function MigrationBanner() {
  const { t, i18n } = useTranslation();
  const { migrationBanner } = useFrontendProperties();
  const [open, setOpen] = useState(() => !wasDismissed());

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      markDismissed();
      setOpen(false);
    }, AUTO_HIDE_MS);
    return () => window.clearTimeout(timer);
  }, [open]);

  const lang = i18n.language?.split("-")[0] ?? "en";
  const title = resolveLocalized(migrationBanner?.titles, lang);
  const message = resolveLocalized(migrationBanner?.messages, lang);

  if (!open || !migrationBanner || (!title && !message)) return null;

  const close = () => {
    markDismissed();
    setOpen(false);
  };

  return (
    <div className={styles.banner} style={{ backgroundColor: migrationBanner.color }} role="status" aria-live="polite">
      <p className={styles.message}>
        {title && <strong>{title}</strong>}
        {title && message ? " " : null}
        {message}
      </p>
      <div className={styles.actions}>
        {(migrationBanner.links ?? []).map((link, index) => (
          <Fragment key={link.url}>
            {index > 0 && (
              <span className={styles.separator} aria-hidden="true">
                ·
              </span>
            )}
            <a className={styles.link} href={link.url} target="_blank" rel="noopener noreferrer">
              {resolveLocalized(link.labels, lang) ?? link.url}
            </a>
          </Fragment>
        ))}
        <IconButton
          color="on-surface"
          variant="icon"
          size="xs"
          icon={{ category: "outlined", type: "close" }}
          onClick={close}
          aria-label={t("common.close")}
        />
      </div>
    </div>
  );
}
