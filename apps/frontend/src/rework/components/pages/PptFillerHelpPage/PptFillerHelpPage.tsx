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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import styles from "./PptFillerHelpPage.module.css";

/**
 * Standalone documentation page for the PPT Filler capability. Opened in a new tab from
 * the agent creation form, so it is a top-level route (no app chrome). The content lives
 * as localized markdown under ``public/`` (``ppt-filler-help.md`` / ``.fr.md``) — text-
 * first and easy to edit, and rendered with the shared rework MarkdownRenderer (same one
 * as the GCU page). The author can later drop screenshots into the markdown.
 */
export default function PptFillerHelpPage() {
  const { i18n } = useTranslation();
  const [markdown, setMarkdown] = useState<string>("");

  useEffect(() => {
    const base = (import.meta.env?.BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
    const lang = i18n.language?.split("-")[0] ?? "en";

    // Only treat a response as real markdown (a dev server may answer index.html for an
    // unknown path); fall back to the English file, then give up gracefully.
    const fetchMd = (path: string) =>
      fetch(`${base}${path}`, { cache: "no-cache" })
        .then((r) => (r.ok ? r.text() : null))
        .then((text) => (text && !text.toLowerCase().includes("<!doctype") ? text : null))
        .catch(() => null);

    const candidates = [`/ppt-filler-help.${lang}.md`, `/ppt-filler-help.md`];

    let cancelled = false;
    candidates
      .reduce((acc, path) => acc.then((text) => text ?? fetchMd(path)), Promise.resolve<string | null>(null))
      .then((text) => {
        if (!cancelled && text) setMarkdown(text);
      });

    return () => {
      cancelled = true;
    };
  }, [i18n.language]);

  return (
    <div className={styles.page}>
      <article className={styles.content}>
        <MarkdownRenderer text={markdown} />
      </article>
    </div>
  );
}
