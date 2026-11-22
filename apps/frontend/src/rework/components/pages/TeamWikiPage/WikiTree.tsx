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

import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { fileIconSpec } from "@rework/utils/fileIconSpec";
import type { WikiPageSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { buildWikiTree, canHaveChild, visibleNodes } from "@rework/features/teamWiki/wikiTree";
import styles from "./WikiTree.module.css";

interface WikiTreeProps {
  pages: readonly WikiPageSummary[];
  rulesPage: WikiPageSummary | null;
  activeSlug: string | null;
  /** Page ids whose children are shown; everything else is folded. */
  expanded: ReadonlySet<string>;
  onToggle: (pageId: string) => void;
  onExpand: (pageId: string) => void;
  onSelect: (slug: string) => void;
  onSelectRules: () => void;
  /** Editors only: start a new page under this one. */
  canEdit: boolean;
  onAddChild: (parent: WikiPageSummary) => void;
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
  expanded,
  onToggle,
  onExpand,
  onSelect,
  onSelectRules,
  canEdit,
  onAddChild,
}: WikiTreeProps) {
  const { t } = useTranslation();
  const tree = useMemo(() => buildWikiTree(pages), [pages]);
  const rows = useMemo(() => visibleNodes(tree, expanded), [tree, expanded]);

  // A flat wiki has no chevrons, so reserving their column on every row would
  // indent the whole rail against nothing. Under a parent, the slot is what
  // keeps a leaf's title aligned with its siblings', so it stays.
  const anyExpandable = rows.some((row) => row.children.length > 0);

  return (
    <nav className={styles.rail} aria-label={t("rework.wiki.tree.ariaLabel")}>
      <ul className={styles.list}>
        {rows.map(({ page, depth, children }) => (
          <li key={page.page_id}>
            <div
              className={`${styles.row} ${page.slug === activeSlug ? styles.rowActive : ""}`}
              style={{ paddingLeft: `calc(var(--spacing-xs) + ${depth} * var(--spacing-m))` }}
            >
              {children.length > 0 ? (
                <IconButton
                  icon={{
                    category: "outlined",
                    type: expanded.has(page.page_id) ? "expand_more" : "chevron_right",
                  }}
                  variant="icon"
                  size="small"
                  onClick={() => onToggle(page.page_id)}
                  aria-label={t(expanded.has(page.page_id) ? "rework.wiki.tree.collapse" : "rework.wiki.tree.expand")}
                />
              ) : (
                anyExpandable && <span className={styles.spacer} aria-hidden="true" />
              )}
              <button
                type="button"
                className={styles.label}
                onClick={() => onSelect(page.slug)}
                aria-current={page.slug === activeSlug ? "page" : undefined}
              >
                {page.kind === "file" && <Icon category="outlined" type={fileIconSpec(page.title, page.mime).type} />}
                <span className={styles.title}>{page.title}</span>
              </button>
              {/* Revealed on hover or keyboard focus. Creating a sub-page by
                  pointing at its parent is what makes the parent unambiguous —
                  no second field to fill, and nothing to get wrong. */}
              {canEdit && page.kind !== "file" && canHaveChild(depth) && (
                <span className={styles.addChild}>
                  {/* The tooltip stays generic while the accessible name keeps
                      the page's title: a pointer already says which row it is
                      on, a screen reader does not. */}
                  <Tooltip text={t("rework.wiki.tree.addChildTooltip")}>
                    <IconButton
                      icon={{ category: "outlined", type: "add" }}
                      variant="icon"
                      size="small"
                      onClick={() => {
                        onExpand(page.page_id);
                        onAddChild(page);
                      }}
                      aria-label={t("rework.wiki.tree.addChild", { title: page.title })}
                    />
                  </Tooltip>
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>

      {rows.length === 0 && <p className={styles.empty}>{t("rework.wiki.tree.empty")}</p>}

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
