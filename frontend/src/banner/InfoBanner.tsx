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
// Generic informative top banner (not tied to any one announcement).
// Announces, persistently and without a dismiss action, whatever platform
// operators configure. Color, texts and links come from the platform-managed
// frontend_settings.properties.infoBanner; without it, nothing renders.
// Rendered once at the app root (see App.tsx), above the routed content, so
// it shows on every page and pushes the rest of the app down instead of
// covering it.
// ---------------------------------------------------------------------------

import { Fragment } from "react";
import { useTranslation } from "react-i18next";
import { useFrontendProperties } from "../hooks/useFrontendProperties";
import styles from "./InfoBanner.module.css";

const resolveLocalized = (map: { [key: string]: string } | undefined | null, lang: string): string | null =>
  map ? (map[lang] ?? map["en"] ?? null) : null;

export default function InfoBanner() {
  const { i18n } = useTranslation();
  const { infoBanner: banner } = useFrontendProperties();

  const lang = i18n.language?.split("-")[0] ?? "en";
  const title = resolveLocalized(banner?.titles, lang);
  const message = resolveLocalized(banner?.messages, lang);

  if (!banner || (!title && !message)) return null;

  return (
    <div className={styles.banner} style={{ backgroundColor: banner.color }} role="status" aria-live="polite">
      <p className={styles.message}>
        {title && <strong>{title}</strong>}
        {title && message ? " " : null}
        {message}
      </p>
      <div className={styles.actions}>
        {(banner.links ?? []).map((link, index) => (
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
      </div>
    </div>
  );
}
