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

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import type { WikiPageSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { buildWikiTree, visibleNodes } from "@rework/features/teamWiki/wikiTree";
import styles from "./WikiTree.module.css";

interface WikiTreeProps {
  pages: readonly WikiPageSummary[];
  rulesPage: WikiPageSummary | null;
  activeSlug: string | null;
  onSelect: (slug: string) => void;
  onSelectRules: () => void;
  /** Filter the tree down to pages an agent touched and nobody has reviewed. */
  reviewOnly: boolean;
  onToggleReviewOnly: () => void;
}

/**
 * The wiki's left rail: the page tree, plus the rules page as its own entry.
 *
 * The rules page is deliberately NOT a node of the tree. It is not content the
 * team browses — it is the instruction sheet every agent reads — so it sits
 * apart, below a separator, where it cannot be confused with an ordinary page
 * or dragged into one.
 */
export function WikiTree({
  pages,
  rulesPage,
  activeSlug,
  onSelect,
  onSelectRules,
  reviewOnly,
  onToggleReviewOnly,
}: WikiTreeProps) {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(new Set());

  const tree = useMemo(() => buildWikiTree(pages), [pages]);
  const pendingReview = useMemo(() => pages.filter((p) => p.needs_review).length, [pages]);

  // Filtering flattens: a matching page whose parent does not match would
  // otherwise vanish with it, and the point of the filter is to find them all.
  const rows = useMemo(() => {
    if (reviewOnly) {
      return pages
        .filter((page) => page.needs_review && page.kind !== "rules")
        .map((page) => ({ page, depth: 0, children: [] }));
    }
    return visibleNodes(tree, collapsed);
  }, [reviewOnly, pages, tree, collapsed]);

  const toggle = (pageId: string) => {
    setCollapsed((current) => {
      const next = new Set(current);
      if (next.has(pageId)) next.delete(pageId);
      else next.add(pageId);
      return next;
    });
  };

  return (
    <nav className={styles.rail} aria-label={t("rework.wiki.tree.ariaLabel")}>
      {/* Kept while the filter is ON even at zero: clearing the last mark would
          otherwise remove the only control that turns the filter off, stranding
          the reader on an empty rail. */}
      {(pendingReview > 0 || reviewOnly) && (
        <button
          type="button"
          className={`${styles.reviewFilter} ${reviewOnly ? styles.reviewFilterOn : ""}`}
          onClick={onToggleReviewOnly}
          aria-pressed={reviewOnly}
        >
          <Icon category="outlined" type="reviews" filled />
          <span>{t("rework.wiki.tree.pendingReview", { count: pendingReview })}</span>
        </button>
      )}

      <ul className={styles.list}>
        {rows.map(({ page, depth, children }) => (
          <li key={page.page_id}>
            <div
              className={`${styles.row} ${page.slug === activeSlug ? styles.rowActive : ""}`}
              style={{ paddingLeft: `calc(var(--spacing-xs) + ${depth} * var(--spacing-m))` }}
            >
              {children.length > 0 && !reviewOnly ? (
                <IconButton
                  icon={{
                    category: "outlined",
                    type: collapsed.has(page.page_id) ? "chevron_right" : "expand_more",
                  }}
                  variant="icon"
                  size="small"
                  onClick={() => toggle(page.page_id)}
                  aria-label={t(collapsed.has(page.page_id) ? "rework.wiki.tree.expand" : "rework.wiki.tree.collapse")}
                />
              ) : (
                <span className={styles.spacer} aria-hidden="true" />
              )}
              <button
                type="button"
                className={styles.label}
                onClick={() => onSelect(page.slug)}
                aria-current={page.slug === activeSlug ? "page" : undefined}
              >
                <span className={styles.title}>{page.title}</span>
                {page.needs_review && <span className={styles.reviewDot} title={t("rework.wiki.tree.needsReview")} />}
              </button>
            </div>
          </li>
        ))}
      </ul>

      {rows.length === 0 && (
        <p className={styles.empty}>{t(reviewOnly ? "rework.wiki.tree.nothingToReview" : "rework.wiki.tree.empty")}</p>
      )}

      {rulesPage !== null && (
        <>
          <hr className={styles.separator} />
          <button
            type="button"
            className={`${styles.rulesRow} ${activeSlug === rulesPage.slug ? styles.rowActive : ""}`}
            onClick={onSelectRules}
            aria-current={activeSlug === rulesPage.slug ? "page" : undefined}
          >
            <Icon category="outlined" type="gavel" filled />
            <span>{t("rework.wiki.rules.title")}</span>
          </button>
        </>
      )}
    </nav>
  );
}
