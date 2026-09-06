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
import Button from "@shared/atoms/Button/Button";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import type { WikiRevisionList } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useUsersByIdsQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { userDisplayName } from "@rework/core/utils/userDisplayName";
import { formatDateTime } from "@rework/utils/formatDateTime";
import styles from "./WikiRevisions.module.css";

interface WikiRevisionsProps {
  /** Kept mounted while closed so it can slide out rather than vanish. */
  open: boolean;
  history: WikiRevisionList | undefined;
  loading: boolean;
  currentRevisionId: string | null;
  canRestore: boolean;
  restoring: boolean;
  onRestore: (revisionId: string) => void;
  onClose: () => void;
}

/**
 * A page's history, and the way back.
 *
 * Restore is what makes an open wiki defensible: anything an agent or a
 * colleague did is one click from being undone, so the protection is
 * reversibility rather than restriction. It publishes a NEW revision carrying
 * the old text — the history is never rewritten, and the restore is itself in
 * it.
 */
export function WikiRevisions({
  open,
  history,
  loading,
  currentRevisionId,
  canRestore,
  restoring,
  onRestore,
  onClose,
}: WikiRevisionsProps) {
  const { t } = useTranslation();
  const [preview, setPreview] = useState<string | null>(null);

  const revisions = useMemo(() => history?.revisions ?? [], [history]);
  const contents = history?.contents ?? {};

  // A revision stores the author's uid. Showing it raw makes the history a
  // column of opaque strings, which is the opposite of what it is for — the
  // point of the panel is knowing WHO changed a page.
  const authorIds = useMemo(
    () => Array.from(new Set(revisions.map((revision) => revision.author_user_id).filter(Boolean))),
    [revisions],
  );
  const { data: authors = [] } = useUsersByIdsQuery({ ids: authorIds }, { skip: authorIds.length === 0 });
  const authorById = useMemo(() => new Map(authors.map((user) => [user.id, user])), [authors]);

  return (
    <aside
      className={`${styles.panel} ${open ? styles.panelOpen : ""}`}
      // Closed, it is off to the side but still in the DOM: `inert` keeps its
      // buttons out of the tab order and out of the accessibility tree.
      inert={!open}
      aria-label={t("rework.wiki.history.title")}
    >
      <header className={styles.header}>
        <h2 className={styles.title}>{t("rework.wiki.history.title")}</h2>
        <IconButton
          icon={{ category: "outlined", type: "close" }}
          variant="icon"
          size="small"
          onClick={onClose}
          aria-label={t("rework.wiki.history.close")}
        />
      </header>

      {loading && (
        <div className={styles.loading}>
          <Spinner />
        </div>
      )}

      {!loading && revisions.length === 0 && <p className={styles.empty}>{t("rework.wiki.history.empty")}</p>}

      <ul className={styles.list}>
        {revisions.map((revision) => {
          const isCurrent = revision.revision_id === currentRevisionId;
          const isOpen = preview === revision.revision_id;
          return (
            <li key={revision.revision_id} className={`${styles.entry} ${isCurrent ? styles.entryCurrent : ""}`}>
              <div className={styles.entryHead}>
                <div className={styles.entryMeta}>
                  <span className={styles.when}>{formatDateTime(revision.created_at)}</span>
                  <span className={styles.who}>
                    {revision.author_kind === "agent" && <Icon category="outlined" type="smart_toy" filled />}
                    {userDisplayName(revision.author_user_id, authorById.get(revision.author_user_id))}
                  </span>
                </div>
                {isCurrent && <span className={styles.currentTag}>{t("rework.wiki.history.current")}</span>}
              </div>

              <div className={styles.entryActions}>
                <Button
                  color="on-surface-retreat"
                  variant="text"
                  size="small"
                  onClick={() => setPreview(isOpen ? null : revision.revision_id)}
                >
                  {t(isOpen ? "rework.wiki.history.hide" : "rework.wiki.history.view")}
                </Button>
                {canRestore && !isCurrent && (
                  <Button
                    color="primary"
                    variant="text"
                    size="small"
                    onClick={() => onRestore(revision.revision_id)}
                    disabled={restoring}
                  >
                    {t("rework.wiki.history.restore")}
                  </Button>
                )}
              </div>

              {isOpen && (
                <div className={styles.preview}>
                  <MarkdownRenderer text={contents[revision.revision_id] ?? ""} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </aside>
  );
}
