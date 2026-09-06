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

import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import type { WikiPageDetail, WikiPageSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { ancestorsOf } from "@rework/features/teamWiki/wikiTree";
import { formatDateTime } from "@rework/utils/formatDateTime";
import styles from "./WikiArticle.module.css";

interface WikiArticleProps {
  /** Display name of the page's last author, already resolved. */
  lastAuthorName: string | null;
  detail: WikiPageDetail;
  pages: readonly WikiPageSummary[];
  canEdit: boolean;
  isRules: boolean;
  onEdit: () => void;
  onOpenHistory: () => void;
  onDelete: () => void;
  onRename: () => void;
  onClearReview: () => void;
  onNavigate: (slug: string) => void;
}

/**
 * Who last changed this page, and when. A reader judging a page an agent may
 * have touched needs the date as much as the name — a wiki entry that has not
 * moved in a year is a different thing from one edited this morning.
 */
function editedLine(t: TFunction, user: string | null, when: string | null): string | null {
  if (user && when) return t("rework.wiki.article.lastEditedByAt", { user, when });
  if (user) return t("rework.wiki.article.lastEditedBy", { user });
  if (when) return t("rework.wiki.article.lastEditedAt", { when });
  return null;
}

/**
 * One wiki page, rendered.
 *
 * Every control above the content is editor-only and simply absent otherwise:
 * a member reads a page that offers them nothing they cannot do, rather than a
 * row of disabled buttons. The server decides either way — hiding is courtesy,
 * not the gate.
 */
export function WikiArticle({
  detail,
  pages,
  lastAuthorName,
  canEdit,
  isRules,
  onEdit,
  onOpenHistory,
  onDelete,
  onRename,
  onClearReview,
  onNavigate,
}: WikiArticleProps) {
  const { t } = useTranslation();
  const { page } = detail;
  const trail = isRules ? [] : ancestorsOf(pages, page.slug);
  const isEmpty = detail.content_md.trim().length === 0;
  const edited = editedLine(t, lastAuthorName, page.updated_at ? formatDateTime(page.updated_at) : null);

  return (
    <article className={styles.article}>
      <header className={styles.header}>
        {trail.length > 0 && (
          <nav className={styles.trail} aria-label={t("rework.wiki.article.breadcrumb")}>
            {trail.map((ancestor) => (
              <button
                key={ancestor.page_id}
                type="button"
                className={styles.trailLink}
                onClick={() => onNavigate(ancestor.slug)}
              >
                {ancestor.title}
              </button>
            ))}
          </nav>
        )}

        <div className={styles.titleRow}>
          <h1 className={styles.title}>{isRules ? t("rework.wiki.rules.title") : page.title}</h1>
          <div className={styles.actions}>
            <div className={styles.tools}>
              {/* History is a read, and the endpoint is member-readable. Who wrote
                  what, and when, is exactly what a reader needs to judge a page
                  an agent may have touched — restore stays editor-only inside. */}
              <IconButton
                icon={{ category: "outlined", type: "history" }}
                variant="icon"
                size="small"
                onClick={onOpenHistory}
                aria-label={t("rework.wiki.article.history")}
              />
              {canEdit && !isRules && (
                <IconButton
                  icon={{ category: "outlined", type: "drive_file_rename_outline" }}
                  variant="icon"
                  size="small"
                  onClick={onRename}
                  aria-label={t("rework.wiki.article.rename")}
                />
              )}
              {canEdit && !isRules && (
                <IconButton
                  icon={{ category: "outlined", type: "delete" }}
                  variant="icon"
                  size="small"
                  onClick={onDelete}
                  aria-label={t("rework.wiki.article.delete")}
                />
              )}
            </div>
            {canEdit && (
              <Button color="primary" variant="filled" size="small" onClick={onEdit}>
                {t("rework.wiki.article.edit")}
              </Button>
            )}
          </div>
        </div>

        {isRules && <p className={styles.rulesNotice}>{t("rework.wiki.rules.notice")}</p>}

        <div className={styles.meta}>
          {detail.author_kind === "agent" && (
            <span className={styles.agentBadge}>
              <Icon category="outlined" type="smart_toy" filled />
              {t("rework.wiki.article.writtenByAgent")}
            </span>
          )}
          {edited && <span>{edited}</span>}
          {page.needs_review && (
            <button
              type="button"
              className={styles.reviewChip}
              onClick={onClearReview}
              disabled={!canEdit}
              title={canEdit ? t("rework.wiki.article.clearReviewHint") : undefined}
            >
              <Icon category="outlined" type="reviews" filled />
              {t(canEdit ? "rework.wiki.article.markReviewed" : "rework.wiki.article.awaitingReview")}
            </button>
          )}
        </div>
      </header>

      {isEmpty ? (
        <p className={styles.emptyBody}>{t(isRules ? "rework.wiki.rules.empty" : "rework.wiki.article.empty")}</p>
      ) : (
        <div className={styles.body}>
          <MarkdownRenderer text={detail.content_md} />
        </div>
      )}
    </article>
  );
}
