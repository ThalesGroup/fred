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
// Warns every user, once per session (i.e. once per login), that the content
// they create now will not survive the switch to the new version.
// Rendered as an overlay over the page content only — never over the sidebar.
// ---------------------------------------------------------------------------

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
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

export default function MigrationBanner() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(() => !wasDismissed());

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      markDismissed();
      setOpen(false);
    }, AUTO_HIDE_MS);
    return () => window.clearTimeout(timer);
  }, [open]);

  if (!open) return null;

  const close = () => {
    markDismissed();
    setOpen(false);
  };

  return (
    <div className={styles.banner} role="status" aria-live="polite">
      <p className={styles.message}>{t("migrationBanner.message")}</p>
      <IconButton
        color="on-surface"
        variant="icon"
        size="xs"
        icon={{ category: "outlined", type: "close" }}
        onClick={close}
        aria-label={t("common.close")}
      />
    </div>
  );
}
