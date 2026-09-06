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

import { useCallback, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import Icon from "@shared/atoms/Icon/Icon";
import IconButton from "@shared/atoms/IconButton/IconButton";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip";
import { MarkdownRenderer } from "@shared/molecules/MarkdownRenderer/MarkdownRenderer";
import {
  useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery,
  type WikiRevisionList,
} from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useUsersByIdsQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useClickOutside } from "@shared/hooks/UseClickOutside";
import { userDisplayName } from "@rework/core/utils/userDisplayName";
import { historyEntries } from "@rework/features/teamWiki/historyEntries";
import { formatDateTime } from "@rework/utils/formatDateTime";
import styles from "./WikiRevisions.module.css";

interface WikiRevisionsProps {
  /** Kept mounted while closed so it can slide out rather than vanish. */
  open: boolean;
  /** Resolves the agent that wrote a revision to its display name. */
  teamId: string;
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
  teamId,
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
  const panelRef = useRef<HTMLElement>(null);

  // Dismissed by clicking away, as an overlay panel should be. No exception for
  // the button that opens it: the panel covers that corner while it is open, so
  // no pointer can reach it — and a keyboard press emits no mousedown.
  const closeOnOutsideClick = useCallback(() => {
    if (open) onClose();
  }, [open, onClose]);
  useClickOutside(panelRef, closeOnOutsideClick);

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

  // Which agent wrote a revision, by name. Only fetched once the history holds
  // an agent revision — most pages never do, and "an agent" reads no worse than
  // a name the user would have to wait for.
  const hasAgentRevision = revisions.some((revision) => revision.agent_instance_id);
  const { data: agentInstances = [] } = useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery(
    { teamId },
    { skip: !teamId || !hasAgentRevision },
  );
  const agentNameById = useMemo(
    () => new Map(agentInstances.map((instance) => [instance.agent_instance_id, instance.display_name])),
    [agentInstances],
  );

  const entries = useMemo(() => historyEntries(revisions), [revisions]);

  const nameOf = (userId: string) => userDisplayName(userId, authorById.get(userId));

  return (
    <aside
      ref={panelRef}
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
        {entries.map((entry) => {
          // A validation is an event, not a version: nothing to preview, nothing
          // to restore, and no current-version outline to claim.
          if (entry.kind === "review") {
            return (
              <li key={entry.key} className={`${styles.entry} ${styles.entryEvent}`}>
                <div className={styles.entryMain}>
                  <span className={styles.what}>
                    <Icon category="outlined" type="check_circle" filled />
                    {t(
                      entry.ofAgentEdit ? "rework.wiki.history.event.agentReview" : "rework.wiki.history.event.review",
                    )}
                  </span>
                  <span className={styles.when}>
                    {formatDateTime(entry.at, { seconds: true })} · {nameOf(entry.by)}
                  </span>
                </div>
              </li>
            );
          }

          const { revision } = entry;
          const isCurrent = revision.revision_id === currentRevisionId;
          const isOpen = preview === revision.revision_id;
          const agentName = revision.agent_instance_id ? agentNameById.get(revision.agent_instance_id) : undefined;
          const what =
            revision.author_kind !== "agent"
              ? t("rework.wiki.history.event.humanEdit")
              : agentName
                ? t("rework.wiki.history.event.agentEdit", { agent: agentName })
                : t("rework.wiki.history.event.agentEditUnnamed");

          return (
            <li key={entry.key} className={`${styles.entry} ${isCurrent ? styles.entryCurrent : ""}`}>
              {/* The whole tile opens the version — a row of buttons under every
                  entry cost more height than the history it was listing. */}
              <button
                type="button"
                className={styles.entryMain}
                aria-expanded={isOpen}
                onClick={() => setPreview(isOpen ? null : revision.revision_id)}
              >
                <span className={styles.what}>
                  {revision.author_kind === "agent" && <Icon category="outlined" type="smart_toy" filled />}
                  {what}
                </span>
                <span className={styles.when}>
                  {formatDateTime(revision.created_at, { seconds: true })} · {nameOf(revision.author_user_id)}
                </span>
              </button>

              {isCurrent ? (
                <span className={styles.currentTag}>{t("rework.wiki.history.current")}</span>
              ) : (
                canRestore && (
                  <span className={styles.corner}>
                    <Tooltip text={t("rework.wiki.history.restore")}>
                      <IconButton
                        icon={{ category: "outlined", type: "history" }}
                        variant="icon"
                        size="small"
                        onClick={() => onRestore(revision.revision_id)}
                        disabled={restoring}
                        aria-label={t("rework.wiki.history.restore")}
                      />
                    </Tooltip>
                  </span>
                )
              )}

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
