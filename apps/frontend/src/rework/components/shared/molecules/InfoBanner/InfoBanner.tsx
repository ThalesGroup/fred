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

// ---------------------------------------------------------------------------
// Generic informative top banner.
// Announces, without a dismiss action, whatever platform operators
// configure. Color, texts and links come from the control-plane
// `platform.frontend.info_banner`, served on the public pre-auth
// `/frontend/config`; without it, nothing renders. Persistent by default;
// `auto_hide_seconds` makes it disappear on its own that long after app
// load. Rendered once at the app root (see App.tsx), above the guards and
// routed content, so it shows on every page — the pre-auth GCU-acceptance
// and root-bootstrap screens included — and pushes the rest of the app down
// instead of covering it.
// ---------------------------------------------------------------------------

import { CSSProperties, Fragment, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getInfoBanner } from "src/common/config";
import { resolveLocalizedText } from "@core/hooks/useLocalizedUploadWarning";
import styles from "./InfoBanner.module.css";

// Config URLs travel through Helm values to an unauthenticated surface, so
// only render links that resolve to http(s) — never `javascript:`/`data:`.
// The base only anchors relative URLs; any base works for scheme detection.
const isSafeHref = (url: string): boolean => {
  try {
    const protocol = new URL(url, "https://base.invalid").protocol;
    return protocol === "http:" || protocol === "https:";
  } catch {
    return false;
  }
};

export default function InfoBanner() {
  const { i18n } = useTranslation();
  const banner = getInfoBanner();
  const autoHideSeconds = banner?.auto_hide_seconds ?? null;
  const [hidden, setHidden] = useState(false);

  // Persistent by default: the timer exists only when the deployer sets
  // `auto_hide_seconds`. The config is loaded once before React renders and
  // the banner mounts once at the app root, so the countdown starts at app
  // load, not per navigation.
  useEffect(() => {
    if (!autoHideSeconds) return;
    const timer = window.setTimeout(() => setHidden(true), autoHideSeconds * 1000);
    return () => window.clearTimeout(timer);
  }, [autoHideSeconds]);

  if (!banner || hidden) return null;

  const title = resolveLocalizedText(banner.titles, i18n.language);
  const message = resolveLocalizedText(banner.messages, i18n.language);
  if (!title && !message) return null;

  const links = (banner.links ?? []).filter((link) => isSafeHref(link.url));

  return (
    <div
      className={styles.banner}
      style={{ "--banner-bg": banner.color } as CSSProperties}
      role="status"
      aria-live="polite"
    >
      <p className={styles.message}>
        {title && <strong>{title}</strong>}
        {title && message && " "}
        {message}
      </p>
      {links.length > 0 && (
        <div className={styles.actions}>
          {links.map((link, index) => (
            <Fragment key={`${index}-${link.url}`}>
              {index > 0 && (
                <span className={styles.separator} aria-hidden="true">
                  ·
                </span>
              )}
              <a className={styles.link} href={link.url} target="_blank" rel="noopener noreferrer">
                {resolveLocalizedText(link.labels, i18n.language) ?? link.url}
              </a>
            </Fragment>
          ))}
        </div>
      )}
    </div>
  );
}
