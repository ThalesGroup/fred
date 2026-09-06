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

// The team wiki (WIKI-02): a tree of Markdown pages read by every member and
// maintained by editors. Slice 2 has no agent involvement at all — the point of
// shipping it first is that a team can judge whether the wiki earns its place
// before anything starts writing into it. Design: rfc/TEAM-WIKI-RFC.md.

import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import { Spinner } from "@shared/atoms/Spinner/Spinner";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Select from "@shared/molecules/Select/Select";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useSelectedTeam } from "../../../../hooks/useSelectedTeam";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities";
import { buildWikiTree, findRulesPage, moveTargets, RULES_PAGE_SLUG } from "@rework/features/teamWiki/wikiTree";
import {
  useCreateWikiPageMutation,
  useDeleteWikiPageMutation,
  usePatchWikiPageMutation,
  useRestoreWikiRevisionMutation,
  useSetWikiReviewMarkMutation,
  useWikiPageQuery,
  useWikiPagesQuery,
  useWikiRevisionsQuery,
  useWikiRulesQuery,
  useWriteWikiPageMutation,
  useWriteWikiRulesMutation,
  useUsersByIdsQuery,
} from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { userDisplayName } from "@rework/core/utils/userDisplayName";
import type { WikiPageSummary } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { WikiArticle } from "./WikiArticle";
import { WikiEditor } from "./WikiEditor";
import { WikiRevisions } from "./WikiRevisions";
import { WikiTree } from "./WikiTree";
import styles from "./TeamWikiPage.module.css";

/** Mirrors the backend's MAX_PAGE_CHARS / MAX_RULES_CHARS. */
const MAX_PAGE_CHARS = 100_000;
const MAX_RULES_CHARS = 4_000;

/** The 409 body the write endpoints return when a base revision is stale. */
interface ConflictBody {
  current_revision_id?: string;
  current_content_md?: string;
}

interface StaleWrite {
  currentContentMd: string;
  /** What the next save must use as its base, or the retry conflicts again. */
  currentRevisionId: string | null;
}

function conflictFrom(error: unknown): StaleWrite | null {
  const status = (error as { status?: number } | undefined)?.status;
  if (status !== 409) return null;
  const data = (error as { data?: ConflictBody } | undefined)?.data;
  return {
    currentContentMd: data?.current_content_md ?? "",
    currentRevisionId: data?.current_revision_id ?? null,
  };
}

function errorText(error: unknown): string {
  const detail = (error as { data?: { detail?: string } } | undefined)?.data?.detail;
  return detail ?? (error as { message?: string } | undefined)?.message ?? String(error);
}

export default function TeamWikiPage() {
  const { t } = useTranslation();
  const { showError } = useToast();
  const navigate = useNavigate();
  const { teamId: routeTeamId, slug } = useParams<{ teamId: string; slug?: string }>();
  const { selectedTeam } = useSelectedTeam();
  const { canUpdateResources: canEdit } = useTeamCapabilities(selectedTeam);
  const teamId = routeTeamId ?? "";

  const [editing, setEditing] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [reviewOnly, setReviewOnly] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  // The page the new one goes under, set by the rail's "+". Null creates a root.
  const [newParent, setNewParent] = useState<WikiPageSummary | null>(null);
  const [renaming, setRenaming] = useState(false);
  const [renameTitle, setRenameTitle] = useState("");
  // Destination of a move, as the select holds it: "" is the root.
  const [renameParentId, setRenameParentId] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [conflict, setConflict] = useState<StaleWrite | null>(null);
  const [editorSeed, setEditorSeed] = useState<string | null>(null);
  // Set when a conflict handed us a newer base. The next save uses this instead
  // of the (now stale) revision the page was loaded with — without it, every
  // retry after a conflict conflicts again.
  const [baseOverride, setBaseOverride] = useState<string | null>(null);
  // Remount key for the editor: MDXEditor reads `markdown` only at mount, so
  // loading someone else's version has to give it a new identity.
  const [editorGeneration, setEditorGeneration] = useState(0);

  const { data: tree, isLoading: treeLoading } = useWikiPagesQuery({ teamId }, { skip: !teamId });
  const pages = useMemo(() => tree?.pages ?? [], [tree]);
  const rulesPage = useMemo(() => findRulesPage(pages), [pages]);

  const isRules = slug === RULES_PAGE_SLUG;
  // The first ROOT of the rendered tree, not the first row of a flat list
  // ordered globally: landing on a nested child while the rail highlights it
  // three levels down reads as a bug.
  const firstSlug = useMemo(() => buildWikiTree(pages)[0]?.page.slug ?? null, [pages]);
  const activeSlug = slug ?? firstSlug;

  const { data: pageDetail, isFetching: pageLoading } = useWikiPageQuery(
    { teamId, slug: activeSlug ?? "" },
    { skip: !teamId || !activeSlug || isRules },
  );
  const { data: rulesDetail, isFetching: rulesLoading } = useWikiRulesQuery({ teamId }, { skip: !teamId || !isRules });
  const detail = isRules ? rulesDetail : pageDetail;

  const { data: history, isFetching: historyLoading } = useWikiRevisionsQuery(
    { teamId, pageId: detail?.page.page_id ?? "" },
    { skip: !showHistory || !detail?.page.page_id },
  );

  const [createPage, { isLoading: creatingPage }] = useCreateWikiPageMutation();
  const [writePage, { isLoading: savingPage }] = useWriteWikiPageMutation();
  const [writeRules, { isLoading: savingRules }] = useWriteWikiRulesMutation();
  const [patchPage] = usePatchWikiPageMutation();
  const [deletePage] = useDeleteWikiPageMutation();
  const [setReviewMark] = useSetWikiReviewMarkMutation();
  const [restoreRevision, { isLoading: restoring }] = useRestoreWikiRevisionMutation();

  // The page stores its last author's uid; the meta line needs their name.
  const lastAuthorId = detail?.page.updated_by ?? null;
  const { data: lastAuthors = [] } = useUsersByIdsQuery(
    { ids: lastAuthorId ? [lastAuthorId] : [] },
    { skip: !lastAuthorId },
  );
  const lastAuthorName = lastAuthorId
    ? userDisplayName(
        lastAuthorId,
        lastAuthors.find((user) => user.id === lastAuthorId),
      )
    : null;

  // Where this page may be moved. The root is always offered; the rest is what
  // the depth cap and the page's own subtree leave available.
  const parentOptions = useMemo(() => {
    const root = { value: "", key: "__root__", label: t("rework.wiki.renameDialog.root") };
    if (!detail) return [root];
    return [
      root,
      ...moveTargets(pages, detail.page.page_id).map((target) => ({
        value: target.page.page_id,
        key: target.page.page_id,
        label: target.path,
      })),
    ];
  }, [pages, detail, t]);

  const goTo = (target: string) => navigate(`/team/${teamId}/wiki/${target}`);

  const leaveEditor = () => {
    setEditing(false);
    setConflict(null);
    setEditorSeed(null);
    setBaseOverride(null);
  };

  // Navigating to another page while the editor is open must close it. Left
  // mounted, its draft would still be in state while `handleSave` now targets
  // the NEW page id — one click from overwriting page B with page A's text.
  useEffect(() => {
    setEditing(false);
    setConflict(null);
    setEditorSeed(null);
    setBaseOverride(null);
    setShowHistory(false);
  }, [slug]);

  const handleSave = async (contentMd: string) => {
    if (!detail) return;
    setConflict(null);
    try {
      const base = baseOverride ?? detail.revision_id;
      if (isRules) {
        await writeRules({
          teamId,
          updateWikiRulesRequest: { content_md: contentMd, base_revision_id: base },
        }).unwrap();
      } else {
        await writePage({
          teamId,
          pageId: detail.page.page_id,
          updateWikiPageContentRequest: { content_md: contentMd, base_revision_id: base },
        }).unwrap();
      }
      leaveEditor();
    } catch (error) {
      // A stale base is the one failure with something useful to offer: the
      // server sends back what landed, so the editor shows it rather than
      // leaving the user to guess what they are about to overwrite. Anything
      // else is a real error and has to be said out loud.
      const stale = conflictFrom(error);
      if (stale) {
        setConflict(stale);
        setBaseOverride(stale.currentRevisionId);
        return;
      }
      showError({ summary: t("rework.wiki.errors.save"), detail: errorText(error) });
    }
  };

  const openCreate = (parent: WikiPageSummary | null) => {
    setNewParent(parent);
    setNewTitle("");
    setCreating(true);
  };

  const closeCreate = () => {
    setCreating(false);
    setNewTitle("");
    setNewParent(null);
  };

  const handleCreate = async () => {
    const title = newTitle.trim();
    if (!title) return;
    try {
      const created = await createPage({
        teamId,
        createWikiPageRequest: { title, content_md: "", parent_page_id: newParent?.page_id ?? null },
      }).unwrap();
      closeCreate();
      goTo(created.page.slug);
    } catch (error) {
      showError({ summary: t("rework.wiki.errors.create"), detail: errorText(error) });
    }
  };

  const handleRename = async () => {
    const title = renameTitle.trim();
    if (!title || !detail) return;
    try {
      await patchPage({
        teamId,
        pageId: detail.page.page_id,
        // `parent_page_id: null` means "leave it where it is", so detaching a
        // page has its own flag — otherwise a move to the root is unsayable.
        updateWikiPageMetadataRequest: renameParentId
          ? { title, parent_page_id: renameParentId }
          : { title, move_to_root: true },
      }).unwrap();
      setRenaming(false);
    } catch (error) {
      showError({ summary: t("rework.wiki.errors.rename"), detail: errorText(error) });
    }
  };

  const handleDelete = async () => {
    if (!detail) return;
    try {
      await deletePage({ teamId, pageId: detail.page.page_id }).unwrap();
      setConfirmDelete(false);
      navigate(`/team/${teamId}/wiki`);
    } catch (error) {
      // The commonest refusal is "delete its children first" — a 409 the user
      // can act on, so it must reach them rather than looking like a dead click.
      showError({ summary: t("rework.wiki.errors.delete"), detail: errorText(error) });
    }
  };

  if (!teamId) {
    return (
      <div className={styles.frame}>
        <div className={styles.page}>
          <div className={styles.state}>{t("rework.wiki.missingTeam")}</div>
        </div>
      </div>
    );
  }

  if (treeLoading) {
    return (
      <div className={styles.frame}>
        <div className={styles.page}>
          <div className={styles.state}>
            <Spinner />
          </div>
        </div>
      </div>
    );
  }

  const hasPages = pages.some((page) => page.kind !== "rules");

  return (
    <div className={styles.frame}>
      <div className={styles.page}>
        <div className={styles.railColumn}>
          <div className={styles.railHeader}>
            <span className={styles.railTitle}>{t("rework.wiki.title")}</span>
            {canEdit && (
              <Button
                color="primary"
                variant="text"
                size="small"
                icon={{ category: "outlined", type: "add" }}
                onClick={() => openCreate(null)}
              >
                {t("rework.wiki.newPage")}
              </Button>
            )}
          </div>
          <WikiTree
            pages={pages}
            rulesPage={rulesPage ?? { page_id: "", slug: RULES_PAGE_SLUG, title: "Rules", kind: "rules" }}
            activeSlug={activeSlug}
            onSelect={goTo}
            onSelectRules={() => goTo(RULES_PAGE_SLUG)}
            canEdit={canEdit}
            onAddChild={(parent) => openCreate(parent)}
            reviewOnly={reviewOnly}
            onToggleReviewOnly={() => setReviewOnly((on) => !on)}
          />
        </div>

        {!hasPages && !isRules ? (
          <PageEmptyState
            icon="book_2"
            message={t(canEdit ? "rework.wiki.empty.editor" : "rework.wiki.empty.member")}
            action={canEdit ? { label: t("rework.wiki.newPage"), onClick: () => openCreate(null) } : undefined}
          />
        ) : pageLoading || rulesLoading ? (
          <div className={styles.state}>
            <Spinner />
          </div>
        ) : !detail ? (
          <div className={styles.state}>{t("rework.wiki.notFound")}</div>
        ) : editing ? (
          <WikiEditor
            key={editorGeneration}
            title={isRules ? t("rework.wiki.rules.title") : detail.page.title}
            initialContent={editorSeed ?? detail.content_md}
            maxChars={isRules ? MAX_RULES_CHARS : MAX_PAGE_CHARS}
            saving={savingPage || savingRules}
            conflict={conflict}
            onSave={handleSave}
            onCancel={leaveEditor}
            onTakeTheirs={(current) => {
              // Remount on the server's text: MDXEditor reads `markdown` only at
              // mount, so changing the prop alone would leave the user's own text
              // on screen while claiming to have loaded theirs. The draft is lost,
              // but they chose that — it was never silently overwritten.
              setEditorSeed(current);
              setConflict(null);
              setEditorGeneration((n) => n + 1);
            }}
          />
        ) : (
          <WikiArticle
            detail={detail}
            pages={pages}
            lastAuthorName={lastAuthorName}
            canEdit={canEdit}
            isRules={isRules}
            onEdit={() => {
              setEditorSeed(null);
              setEditing(true);
            }}
            onOpenHistory={() => setShowHistory(true)}
            onRename={() => {
              setRenameTitle(detail.page.title);
              const parentId = detail.page.parent_page_id;
              setRenameParentId(parentId && pages.some((p) => p.page_id === parentId) ? parentId : "");
              setRenaming(true);
            }}
            onDelete={() => setConfirmDelete(true)}
            onClearReview={() =>
              void setReviewMark({
                teamId,
                pageId: detail.page.page_id,
                setNeedsReviewRequest: { needs_review: false },
              })
            }
            onNavigate={goTo}
          />
        )}

        {showHistory && detail && (
          <WikiRevisions
            history={history}
            loading={historyLoading}
            currentRevisionId={detail.revision_id ?? null}
            canRestore={canEdit}
            restoring={restoring}
            onRestore={(revisionId) => void restoreRevision({ teamId, pageId: detail.page.page_id, revisionId })}
            onClose={() => setShowHistory(false)}
          />
        )}

        <Dialog
          open={creating}
          title={
            newParent
              ? t("rework.wiki.newPageDialog.childTitle", { parent: newParent.title })
              : t("rework.wiki.newPageDialog.title")
          }
          confirmLabel={t("rework.wiki.newPageDialog.confirm")}
          confirmDisabled={!newTitle.trim() || creatingPage}
          onConfirm={() => void handleCreate()}
          onCancel={closeCreate}
        >
          <TextInput
            label={t("rework.wiki.newPageDialog.label")}
            value={newTitle}
            onChange={(event) => setNewTitle(event.target.value)}
            autoFocus
          />
        </Dialog>

        <Dialog
          open={renaming}
          title={t("rework.wiki.renameDialog.title")}
          confirmLabel={t("rework.wiki.renameDialog.confirm")}
          confirmDisabled={!renameTitle.trim()}
          onConfirm={() => void handleRename()}
          onCancel={() => setRenaming(false)}
        >
          <div className={styles.formFields}>
            <TextInput
              label={t("rework.wiki.renameDialog.label")}
              value={renameTitle}
              onChange={(event) => setRenameTitle(event.target.value)}
              autoFocus
            />
            <Select
              size="medium"
              label={t("rework.wiki.renameDialog.parentLabel")}
              value={renameParentId}
              onChange={setRenameParentId}
              options={parentOptions}
            />
          </div>
        </Dialog>

        <ConfirmationDialog
          open={confirmDelete}
          title={t("rework.wiki.deleteDialog.title")}
          message={t("rework.wiki.deleteDialog.message", { title: detail?.page.title ?? "" })}
          confirmLabel={t("rework.wiki.deleteDialog.confirm")}
          criticalAction
          onConfirm={() => void handleDelete()}
          onCancel={() => setConfirmDelete(false)}
        />
      </div>
    </div>
  );
}
