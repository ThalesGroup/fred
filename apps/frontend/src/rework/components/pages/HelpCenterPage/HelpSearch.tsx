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

import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import SearchInput from "@shared/molecules/SearchInput/SearchInput.tsx";
import { helpPagePath, type HelpSectionTree } from "@rework/features/helpCenter/content";
import { searchHelp, type HelpSearchResult } from "@rework/features/helpCenter/search";
import type { HelpLang } from "@rework/features/helpCenter/manifest";
import styles from "./HelpSearch.module.scss";

interface HelpSearchProps {
  lang: HelpLang;
  /** Section id → translated title, for the result's section label. */
  tree: HelpSectionTree[];
}

/**
 * Global help search: a header search field with a results dropdown. The
 * index is built lazily on the first keystroke (search.ts) and cached for the
 * session — nothing runs until the user types. Selecting a result navigates
 * to the page, and to the matched heading's anchor when the hit was a heading.
 */
export default function HelpSearch({ lang, tree }: HelpSearchProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const sectionTitle = useMemo(() => {
    const map = new Map<string, string>();
    for (const section of tree) map.set(section.id, t(section.titleKey));
    return map;
  }, [tree, t]);

  const results = useMemo(() => (query.trim() ? searchHelp(lang, query) : []), [lang, query]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const goToResult = (result: HelpSearchResult) => {
    const path = helpPagePath(lang, result.meta.sectionId, result.meta.id);
    navigate(result.heading ? `${path}#${result.heading.slug}` : path);
    setOpen(false);
    setQuery("");
  };

  const showPanel = open && query.trim().length > 0;

  return (
    <div className={styles.search} ref={containerRef}>
      <SearchInput
        value={query}
        onChange={(value) => {
          setQuery(value);
          setOpen(true);
        }}
        size="small"
        placeholder={t("rework.helpCenter.search.placeholder")}
        ariaLabel={t("rework.helpCenter.search.ariaLabel")}
        clearAriaLabel={t("rework.helpCenter.search.clearAriaLabel")}
      />
      {showPanel && (
        <div className={styles.panel} role="listbox" aria-label={t("rework.helpCenter.search.resultsAria")}>
          {results.length === 0 ? (
            <p className={styles.empty}>{t("rework.helpCenter.search.noResults")}</p>
          ) : (
            results.map((result) => (
              <button
                type="button"
                role="option"
                aria-selected={false}
                key={`${result.meta.sectionId}/${result.meta.id}/${result.heading?.slug ?? ""}`}
                className={styles.result}
                onClick={() => goToResult(result)}
              >
                <span className={styles.resultTitle}>
                  {result.meta.title}
                  {result.heading && <span className={styles.resultHeading}> › {result.heading.text}</span>}
                </span>
                <span className={styles.resultSection}>{sectionTitle.get(result.meta.sectionId)}</span>
                {result.snippet && (
                  <span
                    className={styles.resultSnippet}
                    // Content is HTML-escaped in search.ts; only the <mark> we
                    // wrap around the matched run is injected.
                    dangerouslySetInnerHTML={{ __html: result.snippet }}
                  />
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
