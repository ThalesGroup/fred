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
import { getProperty } from "../../../common/config.tsx";

/** URLs of a legal markdown document, most specific first. A theme archive
 *  shadows the root files, so no theme path appears here. */
export function legalMarkdownCandidates(
  name: string,
  language: string | undefined,
  releaseBrand: string | undefined,
): string[] {
  const lang = language?.split("-")[0] || "en";
  const brand = (releaseBrand || "")
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "");
  const root = [`/${name}.${lang}.md`, `/${name}.md`];
  return brand ? [`/contrib/${brand}/${name}.${lang}.md`, `/contrib/${brand}/${name}.md`, ...root] : root;
}

/** First candidate that answers with markdown. A missing file comes back as
 *  the SPA's index.html, which must not count as a document. */
export async function loadLegalMarkdown(candidates: string[], base: string): Promise<string | null> {
  for (const path of candidates) {
    const text = await fetch(`${base}${path}`, { cache: "no-cache" })
      .then((response) => (response.ok ? response.text() : null))
      .catch(() => null);
    if (text && !text.toLowerCase().includes("<!doctype")) return text;
  }
  return null;
}

export function useLegalMarkdown(name: string): string {
  const { i18n } = useTranslation();
  const [markdown, setMarkdown] = useState("");

  useEffect(() => {
    let cancelled = false;
    const base = (import.meta.env?.BASE_URL as string | undefined)?.replace(/\/$/, "") ?? "";
    loadLegalMarkdown(legalMarkdownCandidates(name, i18n.language, getProperty("releaseBrand")), base).then((text) => {
      if (text && !cancelled) setMarkdown(text);
    });
    return () => {
      cancelled = true;
    };
  }, [name, i18n.language]);

  return markdown;
}
