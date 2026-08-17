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

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fromEvent } from "file-selector";
import { useTranslation } from "react-i18next";
import { useSelector } from "react-redux";
import ResourceExplorer from "@shared/organisms/ResourceExplorer/ResourceExplorer.tsx";
import type { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { FOLDER_ICON, fileIconSpec } from "../../../../utils/fileIconSpec.ts";
import { DocumentUploadDrawer } from "@shared/organisms/DocumentUploadDrawer/DocumentUploadDrawer.tsx";
import {
  MAX_FOLDER_DEPTH,
  exceedsMaxFolderDepth,
  folderPathDepth,
  relativeDirSegments,
} from "@shared/organisms/DocumentUploadDrawer/droppedPaths.ts";
import {
  DocumentViewer,
  DocumentViewerModeToggle,
  type ViewMode,
} from "@shared/organisms/DocumentViewer/DocumentViewer.tsx";
import { InlineDrawer } from "@shared/molecules/InlineDrawer/InlineDrawer.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  type DocumentMetadata,
  type OwnerFilter,
  type TagWithItemsId,
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation,
  useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation,
  useCreateTagKnowledgeFlowV1TagsPostMutation,
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation,
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import {
  buildTree,
  collectDescendantDocUids,
  collectDescendantTagIds,
  findNode,
  fullPath,
  type TagNode,
} from "../../../../../shared/utils/tagTree.ts";
import { selectAllTasks, selectActiveTasks } from "../../../../features/tasks/taskSlice";
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";
import { useRefetchOnTaskSettled } from "../../../../features/tasks/useRefetchOnTaskSettled";
import { useNotifyOnNewTaskTarget } from "../../../../features/tasks/useNotifyOnNewTaskTarget";
import { useDocumentCommands } from "../../../../../components/documents/common/useDocumentCommands";
import { downloadManyAsZip } from "../../../../../utils/downloadUtils.tsx";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useGetTeamQuery, useUsersByIdsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { formatBytes } from "@shared/utils/formatBytes.ts";
import { formatDateTime } from "../../../../utils/formatDateTime.ts";
import { isPdfFile } from "../../../../utils/documentViewerUtils.ts";
import CreateFolderModal from "../CreateFolderModal/CreateFolderModal.tsx";
import ManageLabelsModal from "../ManageLabelsModal/ManageLabelsModal.tsx";
import RenameModal from "../RenameModal/RenameModal.tsx";
import { StatusChip } from "../StatusChip/StatusChip.tsx";
import type { DocStatus } from "@shared/atoms/DocStatusBadge/DocStatusBadge.tsx";
import BulkActionsBar from "../BulkActionsBar/BulkActionsBar.tsx";
import { deriveDocStatus, isTabularOnlyDoc } from "./deriveDocStatus.ts";
import { pagesToRefreshOnTaskCompletion } from "./refreshOnCompletion.ts";
import styles from "./DocumentWorkspace.module.css";

// Hidden 2026-07-30, developer request: undecided whether "Traiter"/"Retraiter"
// stays in the product — flip back to true to restore it. The underlying
// reprocess plumbing (the `reprocess` callback, `reprocessOverrides` pinning,
// the status-poll effect) is untouched, only the row's "more" menu entry
// pointing at it is hidden.
const SHOW_REPROCESS_ACTION = false;

const DEFAULT_PAGE_SIZE = 50;
// Port of main's DocumentLibraryList live-status loop: while a loaded row is
// processing, its folder page is reloaded on this cadence so the badge flips
// to Ready/Failed without a manual refresh.
const DOC_STATUS_POLL_MS = 3000;
// How long a just-reprocessed row stays pinned to "processing" when the
// backend never re-stamps its stages (dead worker, dropped workflow).
const REPROCESS_OVERRIDE_TTL_MS = 90_000;

interface PageState {
  docs: DocumentMetadata[];
  total: number;
  offset: number;
  loading: boolean;
}

interface DocumentWorkspaceProps {
  teamId: string;
  isPersonalTeam: boolean;
  /** Notified after any action that adds or removes a document (upload,
   * single/bulk removal, folder deletion) — lets the parent page's storage
   * stats cards (file count/size by type) refresh without owning any of
   * this workspace's own mutation plumbing. */
  onDocumentsChanged?: () => void;
}

/** The "User Assets" tag is surfaced in its own tab, not in the folder tree. */
const isUserAssetsTag = (name: string, path?: string | null) => name === "User Assets" || path === "user-assets";

type Row = { kind: "folder"; node: TagNode } | { kind: "document"; doc: DocumentMetadata };

type DocMenuAction = "rename" | "download" | "searchable" | "process" | "delete" | "stopIngestion" | "labels";

function rowKey(row: Row): string {
  return row.kind === "folder" ? `folder:${row.node.full}` : `doc:${row.doc.identity.document_uid}`;
}

/** An OS file drag (not a text/element drag) — shared by every drop surface. */
const isFileDrag = (event: React.DragEvent) => event.dataTransfer.types.includes("Files");

// identity.document_name is always "Original file name incl. extension" —
// the source of truth for both display and extension, unlike identity.title
// (see embeddedTitle below).
// Matches the backend's own extension check (Path(name).suffix) in
// rename_document — a rename may never change it (DOCUMENT-RENAME-RFC.md §4).
function documentExtension(doc: DocumentMetadata): string {
  const dot = doc.identity.document_name.lastIndexOf(".");
  return dot > 0 ? doc.identity.document_name.slice(dot) : "";
}

// The Name column always shows document_name: identity.title is populated
// ingestion-time straight from the file's own embedded metadata
// (PDF /Title, docx core_properties.title) with no validation, so it's as
// likely to be empty, a stale value copied from a shared template, or a
// generic "Untitled" placeholder as it is a real paper/document title.
function documentDisplayName(doc: DocumentMetadata): string {
  return doc.identity.document_name;
}

// Surfaced as a hint next to the filename, not as the primary label: still
// useful (e.g. an arXiv PDF's real paper title) when it isn't just noise —
// filtered out when blank or when it doesn't actually add anything over the
// filename itself (base_input_processor.py defaults title to the filename
// stem, so most never-renamed, no-metadata documents would otherwise show an
// identical-looking hint).
function embeddedTitle(doc: DocumentMetadata): string | null {
  const title = doc.identity.title?.trim();
  if (!title) return null;
  const stem = doc.identity.document_name.replace(/\.[^./]+$/, "");
  return title === doc.identity.document_name || title === stem ? null : title;
}

function rowLabel(row: Row): string {
  return row.kind === "folder" ? row.node.name : documentDisplayName(row.doc);
}

/**
 * Corpus d'équipe tab (RFC §13, Resources dashboard v2): breadcrumb drill-down
 * through one library (tag) level at a time — replaces the pre-FRONT-09.G
 * always-expanded tree — with a `DataTable` of the current folder's direct
 * children (subfolders + documents). Heavy listing stays on the backend:
 * folders lazy-load their first document page on entry.
 */
function DocumentWorkspace({ teamId, isPersonalTeam, onDocumentsChanged }: DocumentWorkspaceProps) {
  const { t } = useTranslation();
  const { showSuccess, showError, showWarn } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const activeTasks = useSelector(selectActiveTasks);

  const { data: team } = useGetTeamQuery({ teamId });
  const { canUpdateResources: canCreateFolder } = useTeamCapabilities(team);

  const ownerFilter: OwnerFilter = isPersonalTeam ? "personal" : "team";
  const {
    data: tags,
    isLoading: tagsLoading,
    refetch: refetchTagsQuery,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: "document",
    ownerFilter,
    teamId: isPersonalTeam ? undefined : teamId,
    limit: 10000,
    offset: 0,
  });
  // Every add/delete path in this workspace (upload, single/bulk removal,
  // folder deletion, a newly-registered ingestion task) already calls
  // refetchTags() to refresh the folder tree — piggyback the stats refresh
  // on that same signal instead of threading it through each call site.
  const refetchTags = useCallback(() => {
    onDocumentsChanged?.();
    return refetchTagsQuery();
  }, [refetchTagsQuery, onDocumentsChanged]);

  const tree = useMemo(() => {
    const documentTags = (tags ?? []).filter((tag) => !isUserAssetsTag(tag.name, tag.path));
    return buildTree(documentTags);
  }, [tags]);

  // null => at the Corpus root (the tree's synthetic top node).
  const [currentFolderFull, setCurrentFolderFull] = useState<string | null>(null);
  // Stack of previously-viewed folders, oldest first — the back button pops
  // the most recent one. Not "go to parent": if you drilled in from a
  // search result or a distant breadcrumb click, back returns to wherever
  // you actually came from, which may not be this folder's parent. Whether
  // the button itself is shown/enabled tracks currentFolderFull (are we at
  // the root) instead — navigating to root via the breadcrumb still pushes
  // here like any other navigation, so this stack alone can't answer that.
  const [, setNavigationHistory] = useState<(string | null)[]>([]);
  const [perTag, setPerTag] = useState<Record<string, PageState>>({});
  // Latest page offsets, for the status-poll interval below: it reads them when
  // it fires, and must not resubscribe every time a page loads.
  const perTagRef = useRef(perTag);
  perTagRef.current = perTag;
  const [selectedKeys, setSelectedKeys] = useState<ReadonlySet<string | number>>(new Set());
  const [renameTarget, setRenameTarget] = useState<
    { kind: "folder"; node: TagNode } | { kind: "document"; doc: DocumentMetadata } | null
  >(null);
  // Document whose per-stage ingestion errors are being shown (#2315).
  // The vocabulary query itself lives inside ManageLabelsModal — it only
  // needs to be fetched while that dialog is open, which is exactly this
  // component's own mount lifetime (see the conditional render below).
  const [labelsTarget, setLabelsTarget] = useState<DocumentMetadata | null>(null);
  // "Just reprocessed" rows pinned to "processing" (#1903-era gap): the
  // reprocess route (`POST /process-documents`) returns only the Temporal
  // workflow id — unlike uploads it creates no TaskService task the SSE task
  // feed could follow — and until the workflow stamps `processing.stages` a
  // reload still shows the OLD stages. Each entry keeps its click-time stages
  // snapshot; the override is dropped as soon as the backend visibly
  // re-stamps the document (snapshot mismatch) or the TTL passes.
  const [reprocessOverrides, setReprocessOverrides] = useState<Record<string, { snapshot: string; deadline: number }>>(
    {},
  );
  // The live ingestion task backing each row, keyed by document uid (#2315).
  // The browse snapshot's `processing.stages` lags the worker — a stage is
  // stamped `in_progress` only once the activity starts, and nothing refetches
  // the row before the task finishes — so deriving the badge from the snapshot
  // alone reads "raw" for the whole run (and a short run never shows
  // "processing" at all). The SSE task feed already carries the live state
  // with `target.id = document_uid`; the same map also resolves which task the
  // row's stop-ingestion action must cancel.
  const activeDocTaskByUid = useMemo(() => {
    const byUid = new Map<string, TaskViewModel>();
    for (const task of activeTasks) {
      if (task.target?.type === "document" && task.target.id) byUid.set(task.target.id, task);
    }
    return byUid;
  }, [activeTasks]);
  // Documents whose ingestion finished during THIS browser session — they get
  // a small "just finished" dot on their otherwise-silent ready state. The
  // task feed lives in Redux memory, so a refresh clears the set by itself;
  // that ephemerality is the feature (spot what just finished), not a bug.
  const allTasks = useSelector(selectAllTasks);
  const justCompletedDocUids = useMemo(() => {
    const uids = new Set<string>();
    for (const task of allTasks) {
      if (task.state === "succeeded" && task.target?.type === "document" && task.target.id) uids.add(task.target.id);
    }
    return uids;
  }, [allTasks]);
  // A just-reprocessed doc must read as "processing" even though its stale
  // `processing.stages` snapshot hasn't caught up yet — see reprocessOverrides
  // above. Centralized here since every status-driven cell (menu label,
  // StatusChip, excluded-from-search gating) needs the same override applied.
  const getDocStatus = (doc: DocumentMetadata): DocStatus =>
    reprocessOverrides[doc.identity.document_uid]
      ? "processing"
      : deriveDocStatus(doc, activeDocTaskByUid.get(doc.identity.document_uid)).status;
  const [uploadOpen, setUploadOpen] = useState(false);
  // Files dropped on a folder row, handed to the upload drawer as its initial list;
  // cleared on close so a later "+"-opened drawer starts empty.
  const [droppedFiles, setDroppedFiles] = useState<File[] | undefined>(undefined);
  // Set only when the upload drawer was opened by dropping files onto a
  // folder row — the drop target is not necessarily the folder currently
  // being viewed, so it overrides destinationPath/tags for that one upload
  // without changing navigation. Cleared alongside droppedFiles on close.
  const [dropTargetNode, setDropTargetNode] = useState<TagNode | null>(null);
  const [dragOverFolder, setDragOverFolder] = useState<string | null>(null);
  // OS-file drag hovering anywhere over the opened folder's page (not a
  // specific folder row) — drives the full-page "drop here" overlay.
  const [pageDragOver, setPageDragOver] = useState(false);
  // Folder tags created (or resolved) while the CURRENT upload drawer is open,
  // keyed by full path — sibling subdirectories of one dropped folder share
  // parent chains through it instead of racing duplicate POST /tags. Cleared
  // when the drawer closes: a folder deleted later must not resurrect its id.
  const pendingFolderTagIds = useRef(new Map<string, string>());
  const [createOpen, setCreateOpen] = useState(false);
  // Client-side filter over the current folder's already-loaded rows — not
  // the deferred server-side search from RFC §13.4 (POST .../browse's
  // `query` field), which would search across the whole library, not just
  // what's on screen. Same pattern as the team members table's search.
  const [search, setSearch] = useState("");
  // Shared across the whole browser (not per-tag) — matches how the members
  // table's rows-per-page selector is one setting for the whole DataTable.
  const [rowsPerPage, setRowsPerPage] = useState(DEFAULT_PAGE_SIZE);

  const [browseDocumentsByTag] = useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();
  const [fetchTagSizes] = useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation();
  const [processDocuments] = useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation();
  const [deleteTag] = useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation();
  const [cancelTask] = useCancelTaskKnowledgeFlowV1TasksTaskIdCancelPostMutation();
  const [createTag] = useCreateTagKnowledgeFlowV1TagsPostMutation();

  const currentNode = currentFolderFull ? findNode(tree, currentFolderFull) : tree;
  const currentTag = currentNode.tagsHere[0] ?? null;

  const loadTagPage = useCallback(
    async (tagId: string, offset: number, limit: number = rowsPerPage) => {
      setPerTag((prev) => ({
        ...prev,
        [tagId]: { docs: prev[tagId]?.docs ?? [], total: prev[tagId]?.total ?? 0, offset, loading: true },
      }));
      try {
        const res = await browseDocumentsByTag({
          browseDocumentsByTagRequest: { tag_id: tagId, offset, limit },
        }).unwrap();
        setPerTag((prev) => ({
          ...prev,
          [tagId]: { docs: res.documents ?? [], total: res.total ?? 0, offset, loading: false },
        }));
      } catch {
        setPerTag((prev) => ({ ...prev, [tagId]: { ...prev[tagId], loading: false } as PageState }));
      }
    },
    [browseDocumentsByTag, rowsPerPage],
  );

  const handleRowsPerPageChange = useCallback(
    (limit: number) => {
      setRowsPerPage(limit);
      if (currentTag) void loadTagPage(currentTag.id, 0, limit);
    },
    [currentTag, loadTagPage],
  );

  const navigateTo = useCallback(
    (full: string | null) => {
      setNavigationHistory((prev) => [...prev, currentFolderFull]);
      setCurrentFolderFull(full);
      setSelectedKeys(new Set());
    },
    [currentFolderFull],
  );

  const navigateBack = useCallback(() => {
    setNavigationHistory((prev) => {
      if (prev.length === 0) return prev;
      setCurrentFolderFull(prev[prev.length - 1]);
      setSelectedKeys(new Set());
      return prev.slice(0, -1);
    });
  }, []);

  // Load the current folder's document page on EVERY entry, not just the first:
  // a folder opened while its files were still uploading (or their fresh ReBAC
  // tuples still propagating server-side) would otherwise stay frozen on that
  // first empty snapshot forever — none of the other refresh paths retries a
  // page that doesn't yet SHOW the document (the 3s poll needs a visible
  // processing row, useRefetchOnTaskSettled needs the doc already in the page,
  // useNotifyOnNewTaskTarget fires before this page exists). loadTagPage keeps
  // the previous rows while reloading, so re-entering an already-loaded folder
  // refreshes without a flash of empty.
  const currentTagId = currentTag?.id ?? null;
  useEffect(() => {
    if (currentTagId) void loadTagPage(currentTagId, 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- keyed on the
    // folder identity alone: one load per ENTRY is the contract, so nothing
    // else may retrigger it. loadTagPage is deliberately not a dep — its
    // identity tracks rowsPerPage (whose change already reloads explicitly
    // via handleRowsPerPageChange), and any harness that rebuilds the browse
    // trigger per render would otherwise refire this into a reload loop.
  }, [currentTagId]);

  // Drop an override once the backend visibly re-stamped the document (its
  // fresh stages no longer match the click-time snapshot — the real derived
  // status takes over) or its safety deadline passed.
  useEffect(() => {
    const uids = Object.keys(reprocessOverrides);
    if (uids.length === 0) return;
    const now = Date.now();
    const stale = new Set<string>();
    for (const uid of uids) {
      const entry = reprocessOverrides[uid];
      if (entry.deadline < now) {
        stale.add(uid);
        continue;
      }
      for (const page of Object.values(perTag)) {
        const doc = page.docs.find((d) => d.identity.document_uid === uid);
        if (doc && JSON.stringify(doc.processing?.stages ?? {}) !== entry.snapshot) stale.add(uid);
      }
    }
    if (stale.size > 0) {
      setReprocessOverrides((prev) => Object.fromEntries(Object.entries(prev).filter(([uid]) => !stale.has(uid))));
    }
  }, [perTag, reprocessOverrides]);

  // Port of main's DocumentLibraryList polling loop: while any loaded row is
  // (or is pinned) "processing", reload the folder pages showing it so the
  // badge flips to Ready/Failed without a manual refresh.
  const pendingTagIds = useMemo(
    () =>
      Object.entries(perTag)
        .filter(([, page]) => page.docs.some((doc) => getDocStatus(doc) === "processing"))
        .map(([tagId]) => tagId),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- getDocStatus is
    // rebuilt every render; its inputs (perTag, the overrides and the live task
    // map) are the real dependencies.
    [perTag, reprocessOverrides, activeDocTaskByUid],
  );
  // While any ingestion is live, poll the folder being viewed too, even if its
  // loaded page shows no processing row yet: a subfolder entered before its
  // files' uploads (or their fresh ReBAC tuples) landed keeps an empty
  // snapshot that no other refresh path retries — this loop picks the rows up
  // as they become visible, with their live "processing" badge.
  const pollTagIds =
    activeDocTaskByUid.size > 0 && currentTagId && !pendingTagIds.includes(currentTagId)
      ? [...pendingTagIds, currentTagId]
      : pendingTagIds;
  // Keyed on the ids themselves, not the array identity: the live task map is a
  // new object on every SSE event, and depending on it directly tore down and
  // restarted the interval on each one — so during a bulk ingestion, when this
  // refresh matters most, the 3s never elapsed and the folder never reloaded.
  const pendingTagKey = pollTagIds.join(",");
  useEffect(() => {
    if (!pendingTagKey) return;
    const interval = setInterval(() => {
      for (const tagId of pendingTagKey.split(",")) void loadTagPage(tagId, perTagRef.current[tagId]?.offset ?? 0);
    }, DOC_STATUS_POLL_MS);
    return () => clearInterval(interval);
  }, [pendingTagKey, loadTagPage, perTagRef]);

  const commands = useDocumentCommands({
    refetchTags,
    refetchDocs: async (tagId?: string) => {
      if (tagId) await loadTagPage(tagId, perTag[tagId]?.offset ?? 0);
    },
  });
  // The Fichier/Raw toggle lives in the preview drawer's own header (next to
  // its close button), not inside DocumentViewer's body — so this workspace,
  // not the viewer, owns which mode is showing. Reset to "file" on every new
  // target so a previous document's "Raw" choice doesn't leak into the next.
  const [previewView, setPreviewView] = useState<ViewMode>("file");
  useEffect(() => {
    setPreviewView("file");
  }, [commands.previewTarget?.documentUid]);

  // When an ingestion task settles, the browse snapshot that backs its row is
  // stale (still "raw") and would need a manual refresh to show "Ready". Reload
  // just the loaded folder page(s) showing that document so its status goes live.
  // Also the moment the storage quota moves, in both directions:
  //   - success: ingestion saves the metadata (and its file size) at the end of
  //     the workflow, so the earlier refetchTags() at task registration ran
  //     while the document still weighed nothing;
  //   - cancel: the backend erases the half-built document and gives its quota
  //     back (`delete_cancelled_document`), seconds after the cancel request
  //     returned — far too late for confirmStopIngestion to refetch anything
  //     itself, which is why it deliberately does not try.
  // Without this notification the quota meter stays behind by exactly the
  // document that just landed, or the one that was just erased.
  useRefetchOnTaskSettled("document", (documentUid) => {
    onDocumentsChanged?.();
    for (const [tagId, page] of Object.entries(perTag)) {
      if (page.docs.some((doc) => doc.identity.document_uid === documentUid)) {
        void loadTagPage(tagId, page.offset);
      }
    }
  });

  // A brand-new document (just registered by the upload drawer) has no row
  // anywhere yet, so `useRefetchOnTaskSettled` above can never trigger its first
  // refetch — its check requires the document to already be in a loaded page.
  // Fire on first sighting of the task instead (any state, not just succeeded).
  useNotifyOnNewTaskTarget("document", () => {
    void refetchTags();
    for (const [tagId, page] of Object.entries(perTag)) {
      void loadTagPage(tagId, page.offset);
    }
  });

  const reprocess = useCallback(
    async (doc: DocumentMetadata, tagId: string) => {
      try {
        await processDocuments({
          processDocumentsRequest: {
            files: [
              {
                source_tag: doc.source?.source_tag ?? "",
                document_uid: doc.identity.document_uid,
                profile: "fast",
                tags: doc.tags?.tag_ids ?? [tagId],
              },
            ],
            pipeline_name: "profile-fast",
          },
        }).unwrap();
        showSuccess?.({ summary: t("rework.resources.toast.processStarted") });
        setReprocessOverrides((prev) => ({
          ...prev,
          [doc.identity.document_uid]: {
            snapshot: JSON.stringify(doc.processing?.stages ?? {}),
            deadline: Date.now() + REPROCESS_OVERRIDE_TTL_MS,
          },
        }));
        await loadTagPage(tagId, perTag[tagId]?.offset ?? 0);
      } catch (e: unknown) {
        showError?.({
          summary: t("validation.error"),
          detail: (e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.toast.processError"),
        });
      }
    },
    [processDocuments, showSuccess, showError, t, loadTagPage, perTag],
  );

  // Deletes the folder's tag; the backend cascades to sub-folders and untags/
  // deletes their documents (TagPermission.DELETE, tag_service.py), so this is
  // safe to offer for both empty and populated folders — the confirmation
  // message just makes the blast radius explicit before it happens.
  //
  // That number is counted at click time over the folder AND its sub-folders,
  // never read from the tag list's `item_ids`, which was wrong in both
  // directions. Too high: `item_ids` only refreshes when this workspace itself
  // mutates something, so a document the backend removed on its own — a
  // cancelled ingestion erasing its half-built document (#2315), the OPS-04
  // sweeper — stayed counted, and the dialog announced 4 documents for a folder
  // showing 1. Too low: it covers the folder's own documents only, while
  // `delete_tag` recurses into every sub-tag — under-announcing what is about
  // to be destroyed, which is the direction that actually costs data.
  const confirmDeleteFolder = useCallback(
    async (node: TagNode) => {
      const tag = node.tagsHere[0];
      if (!tag) return;
      // One `total` per tag in the subtree, `limit: 1` so the response carries a
      // count and not a page of documents. Summing across the subtree cannot
      // double-count: a document is tagged into exactly one folder, the same
      // invariant the folder-size column relies on.
      let docCount: number | null = null;
      try {
        const pages = await Promise.all(
          collectDescendantTagIds(node).map((tagId) =>
            browseDocumentsByTag({ browseDocumentsByTagRequest: { tag_id: tagId, offset: 0, limit: 1 } }).unwrap(),
          ),
        );
        docCount = pages.reduce((sum, page) => sum + (page.total ?? 0), 0);
      } catch {
        // Counting failed — still offer the deletion, but promise no number
        // rather than a number that might be wrong.
      }
      showConfirmationDialog({
        title: t("rework.resources.confirm.deleteFolderTitle"),
        message:
          docCount === null || (docCount === 0 && node.children.size > 0)
            ? t("rework.resources.confirm.deleteFolderMessageUnknownCount", { name: node.name })
            : docCount > 0
              ? t("rework.resources.confirm.deleteFolderMessageWithDocs", { name: node.name, count: docCount })
              : t("rework.resources.confirm.deleteFolderMessageEmpty", { name: node.name }),
        onConfirm: () =>
          void deleteTag({ tagId: tag.id })
            .unwrap()
            .then(() => {
              showSuccess?.({ summary: t("rework.resources.toast.deleteFolderSuccess") });
              if (currentFolderFull === node.full)
                navigateTo(node.full.includes("/") ? node.full.split("/").slice(0, -1).join("/") : null);
              void refetchTags();
            })
            .catch((e: unknown) => {
              showError?.({
                summary: t("validation.error"),
                detail:
                  (e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.toast.deleteFolderError"),
              });
            }),
      });
    },
    [
      browseDocumentsByTag,
      deleteTag,
      showConfirmationDialog,
      showSuccess,
      showError,
      t,
      refetchTags,
      currentFolderFull,
      navigateTo,
    ],
  );

  // Cooperative cancel of the live ingestion task backing this row (#2315) —
  // the task id comes from the same SSE map the status badge reads. The cancel
  // is a request, not the outcome: the row keeps reading "processing" until the
  // executor's verdict lands (the OPS-04 sweeper flips the task to `cancelled`
  // and fails the document's stuck stages via `on_reconciled_terminal`,
  // document_failure.py), so the toast is the only immediate acknowledgement.
  const confirmStopIngestion = useCallback(
    (doc: DocumentMetadata) => {
      const task = activeDocTaskByUid.get(doc.identity.document_uid);
      if (!task) return;
      showConfirmationDialog({
        title: t("rework.resources.confirm.stopIngestionTitle"),
        message: t("rework.resources.confirm.stopIngestionMessage", { name: documentDisplayName(doc) }),
        onConfirm: () =>
          void cancelTask({ taskId: task.taskId })
            .unwrap()
            .then(() => showSuccess?.({ summary: t("rework.resources.toast.stopIngestionRequested") }))
            .catch((e: unknown) => {
              showError?.({
                summary: t("validation.error"),
                detail:
                  (e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.toast.stopIngestionError"),
              });
            }),
      });
    },
    [activeDocTaskByUid, cancelTask, showConfirmationDialog, showSuccess, showError, t],
  );

  // Derived from the same map the badge and the row menu read, so "this row has
  // a live ingestion" has one definition in this page instead of three.
  const runningDocIds = useMemo(
    () => new Set([...activeDocTaskByUid].filter(([, task]) => task.state !== "failed").map(([uid]) => uid)),
    [activeDocTaskByUid],
  );

  const prevRunningDocIdsRef = useMemo(() => ({ current: new Set<string | undefined>() }), []);
  useEffect(() => {
    const pages = pagesToRefreshOnTaskCompletion(prevRunningDocIdsRef.current, runningDocIds, perTag);
    prevRunningDocIdsRef.current = runningDocIds;
    for (const { tagId, offset } of pages) void loadTagPage(tagId, offset);
  }, [runningDocIds, perTag, loadTagPage, prevRunningDocIdsRef]);

  /** Seed the ingestion drawer with an OS-file drop, targeting `node`.
   * `requireDir` (the corpus root, where a file can only live inside a
   * library): keep only files that came out of a dropped folder — their
   * chain becomes the library — and reject loose ones, with a toast. */
  const openDrawerWithDroppedFiles = (event: React.DragEvent, node: TagNode, requireDir = false) => {
    event.preventDefault();
    // fromEvent must start synchronously: the DataTransfer entries needed to
    // walk a dropped directory are dead once the drop handler has returned.
    void fromEvent(event.nativeEvent).then((items) => {
      let dropped = items.filter((item): item is File => item instanceof File);
      if (requireDir) {
        const foldered = dropped.filter((file) => relativeDirSegments(file).length > 0);
        if (foldered.length === 0) {
          if (dropped.length > 0)
            showError?.({
              summary: t("rework.resources.rootDrop.rejectedTitle"),
              detail: t("rework.resources.rootDrop.rejectedDetail"),
            });
          return;
        }
        if (foldered.length < dropped.length)
          showWarn?.({
            summary: t("rework.resources.rootDrop.rejectedTitle"),
            detail: t("rework.resources.rootDrop.skippedDetail", { count: dropped.length - foldered.length }),
          });
        dropped = foldered;
      }
      // Depth guardrail (#2355): a file may not end up nested deeper than
      // MAX_FOLDER_DEPTH levels, destination included — the mirrored tag
      // chain is bounded the same way server-side (422 past the cap).
      const destinationDepth = folderPathDepth(node.full);
      const shallow = dropped.filter((file) => !exceedsMaxFolderDepth(file, destinationDepth));
      if (shallow.length < dropped.length) {
        if (shallow.length === 0) {
          showError?.({
            summary: t("documentLibrary.tooDeepTitle"),
            detail: t("documentLibrary.tooDeepRejected", { max: MAX_FOLDER_DEPTH }),
          });
          return;
        }
        showWarn?.({
          summary: t("documentLibrary.tooDeepTitle"),
          detail: t("documentLibrary.tooDeepSkipped", {
            count: dropped.length - shallow.length,
            max: MAX_FOLDER_DEPTH,
          }),
        });
        dropped = shallow;
      }
      if (dropped.length === 0) return;
      setDropTargetNode(node);
      setDroppedFiles(dropped);
      setUploadOpen(true);
    });
  };

  /** OS-file drag-and-drop onto a folder row: pre-select that folder and open the
   * ingestion drawer seeded with the dropped files. Same gating as the row's
   * upload action. */
  const folderDropProps = (node: TagNode, droppable: boolean) => {
    if (!droppable) return {};
    return {
      "data-drag-over": dragOverFolder === node.full || undefined,
      onDragOver: (event: React.DragEvent) => {
        if (!isFileDrag(event)) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = "copy";
      },
      onDragEnter: (event: React.DragEvent) => {
        if (!isFileDrag(event)) return;
        setDragOverFolder(node.full);
      },
      onDragLeave: (event: React.DragEvent) => {
        if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
        setDragOverFolder((prev) => (prev === node.full ? null : prev));
      },
      onDrop: (event: React.DragEvent) => {
        // The whole page is a drop surface for the opened folder — a drop that
        // landed on this row must not bubble up and hit that target too.
        event.stopPropagation();
        setDragOverFolder(null);
        openDrawerWithDroppedFiles(event, node);
      },
    };
  };

  const page = currentTag ? perTag[currentTag.id] : undefined;
  const childFolders = useMemo(
    () => [...currentNode.children.values()].sort((a, b) => a.name.localeCompare(b.name)),
    [currentNode],
  );

  // Folder rows show the total size of every document the folder contains,
  // including its subfolders' — a folder tag's own item_ids never cover
  // nested tags, so this walks the (already fully loaded) in-memory tree via
  // collectDescendantTagIds, batched once per folder view via
  // /documents/metadata/tag-sizes for the union of every visible folder's own
  // + descendant tag ids, not one query per row. Per-tag sums are summed
  // client-side per folder: safe against double counting because a document
  // is tagged into exactly one folder (its leaf tag), never simultaneously
  // into an ancestor folder too — verified against real data (folder total +
  // subfolder total == the team's whole storage counter, no overlap).
  const [folderSizes, setFolderSizes] = useState<Record<string, number>>({});
  const folderDescendantTagIds = useMemo(
    () => new Map(childFolders.map((node) => [node.full, collectDescendantTagIds(node)])),
    [childFolders],
  );
  const folderTagIds = useMemo(
    () => Array.from(new Set([...folderDescendantTagIds.values()].flat())),
    [folderDescendantTagIds],
  );
  // Keyed by sorted content, not the array's own identity: `tags` (and so
  // `childFolders`/`folderTagIds`) can get a fresh reference on a render that
  // doesn't actually change which folders are shown, and re-issuing the same
  // batch call on every such render would both waste requests and, since each
  // resolution replaces `folderSizes` wholesale, loop forever.
  const folderTagIdsKey = [...folderTagIds].sort().join(",");
  const fetchedSizesKeyRef = useRef<string>("");
  useEffect(() => {
    if (folderTagIds.length === 0 || folderTagIdsKey === fetchedSizesKeyRef.current) return;
    fetchedSizesKeyRef.current = folderTagIdsKey;
    (async () => {
      try {
        const res = await fetchTagSizes({ tagSizesRequest: { tag_ids: folderTagIds } }).unwrap();
        setFolderSizes((prev) => ({ ...prev, ...res.sizes }));
      } catch {
        // Sizes stay unresolved for these tag ids — the cell keeps showing "—".
      }
    })();
    // folderTagIds itself is intentionally not a dep: folderTagIdsKey already
    // captures every content change it could cause, and it's recomputed fresh
    // in this same render anyway.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [folderTagIdsKey, fetchTagSizes]);

  // #2384 — a folder row carries a "processing" chip while ANY document under
  // it (its own + every sub-folder's, at any depth) is still being ingested.
  // Without it, the only way to tell whether a bulk upload has finished is to
  // walk into every sub-folder and look for still-processing rows.
  //
  // Two evidence sources, unioned — neither subsumes the other:
  //  - `pendingTagIds`: tags whose ALREADY-LOADED page shows a processing row.
  //    This is the same derived status the rows themselves render, so it also
  //    covers what the browse snapshot alone knows and the task feed does not
  //    (a teammate's ingestion, a document left `in_progress` by a dead
  //    worker). Limited to folders visited this session — but without it a
  //    folder could read "settled" while a row inside it visibly spins, the
  //    exact confusion this feature exists to remove.
  //  - the live SSE task feed (`activeDocTaskByUid`, the signal the document
  //    badge reads since #2315) matched against the tag tree's `item_ids`.
  //    Reaches folders that were never opened, but carries only the current
  //    user's tasks (`GET /tasks?scope=user`, useTaskRehydration).
  //
  // Deliberately never aggregates failure: `selectActiveTasks` drops every
  // terminal state and `pendingTagIds` counts `processing` only, so the chip
  // clears itself the moment the last child settles — whichever way it
  // settled. A failed ingestion stays announced on its own document row,
  // where the per-stage error tooltip is.
  const pendingTagIdsKey = pendingTagIds.join(",");
  const activeDocUidKey = [...activeDocTaskByUid.keys()].sort().join(",");
  const ingestingFolders = useMemo(() => {
    const marked = new Set<string>();
    const pending = new Set(pendingTagIds);
    // Unlike the tag-id walk, this one is O(documents in the subtree) — and
    // the tag list refetches once per uploaded file (useNotifyOnNewTaskTarget),
    // so it is skipped entirely whenever nothing is live, which is the steady
    // state. Iterating the (small) live-task list against each folder's uid set
    // rather than the reverse keeps the match itself cheap.
    const liveUids = [...activeDocTaskByUid.keys()];
    for (const node of childFolders) {
      if ((folderDescendantTagIds.get(node.full) ?? []).some((id) => pending.has(id))) {
        marked.add(node.full);
        continue;
      }
      if (liveUids.length === 0) continue;
      const docUids = collectDescendantDocUids(node);
      if (liveUids.some((uid) => docUids.has(uid))) marked.add(node.full);
    }
    return marked;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- both live inputs
    // are read through stable string keys instead of their own identities: the
    // task map (and so `pendingTagIds`) is a fresh object on EVERY SSE progress
    // event, and depending on it directly would re-walk the tree on each one —
    // the same trap `pendingTagKey` avoids for the poll interval above. Read
    // from the sources, not from the keys: a document uid is not always a plain
    // uuid (scheduler pulls build `pull-{source_tag}-{hash}`), so splitting the
    // key back apart would be wrong.
  }, [childFolders, folderDescendantTagIds, pendingTagIdsKey, activeDocUidKey]);

  const rows: Row[] = useMemo(
    () => [
      ...childFolders.map((node): Row => ({ kind: "folder", node })),
      ...(page?.docs ?? []).map((doc): Row => ({ kind: "document", doc })),
    ],
    [childFolders, page?.docs],
  );

  const filteredRows = useMemo(() => {
    const trimmed = search.trim().toLowerCase();
    if (!trimmed) return rows;
    return rows.filter((row) => rowLabel(row).toLowerCase().includes(trimmed));
  }, [rows, search]);

  // Batched once for the whole page (not one query per row, same pattern as
  // TeamAgentsPage's audit-user resolution, #2096) — the Auteur column shows
  // the uploader's display name, resolved from their uid.
  const uploaderUids = useMemo(
    () =>
      Array.from(
        new Set((page?.docs ?? []).map((doc) => doc.identity.uploaded_by).filter((uid): uid is string => Boolean(uid))),
      ),
    [page?.docs],
  );
  const { data: uploaders = [], isFetching: isFetchingUploaders } = useUsersByIdsQuery(
    { ids: uploaderUids },
    { skip: uploaderUids.length === 0 },
  );
  const uploaderById = useMemo(() => new Map(uploaders.map((summary) => [summary.id, summary])), [uploaders]);

  const selectedDocs = useMemo(
    () =>
      filteredRows
        .filter((row): row is Row & { kind: "document" } => row.kind === "document" && selectedKeys.has(rowKey(row)))
        .map((row) => row.doc),
    [filteredRows, selectedKeys],
  );

  const bulkDelete = () => {
    if (!currentTag || selectedDocs.length === 0) return;
    showConfirmationDialog({
      title: t("rework.resources.confirm.deleteTitle"),
      message: t("rework.resources.confirm.deleteBulkMessage", { count: selectedDocs.length }),
      onConfirm: () => {
        void commands.bulkRemoveFromLibraryForTag(selectedDocs, currentTag as unknown as TagWithItemsId);
        setSelectedKeys(new Set());
      },
    });
  };

  // "exclude" when every toggle-relevant selected doc is currently searchable,
  // "include" when every one is already excluded, undefined (button hidden, per
  // BulkActionsBar's "omit to hide" convention) on a mixed selection — there's
  // no single unambiguous action to offer for a set of files in both states at
  // once. A tabular-only dataset's `retrievable` is always false without being
  // a real exclusion (see isTabularOnlyDoc) — excluded from this computation
  // entirely, not counted toward either direction, same as if it weren't
  // selected at all.
  const searchToggleMode = useMemo<"exclude" | "include" | undefined>(() => {
    const toggleable = selectedDocs.filter((doc) => !isTabularOnlyDoc(doc));
    if (toggleable.length === 0) return undefined;
    const excludedCount = toggleable.filter((doc) => doc.source.retrievable === false).length;
    if (excludedCount === 0) return "exclude";
    if (excludedCount === toggleable.length) return "include";
    return undefined;
  }, [selectedDocs]);

  // toggleRetrievable only calls the backend — it never touches `perTag`, so
  // without this the row's icon/menu label (both derived straight from
  // `row.doc.source.retrievable`) stay stale until the folder is reloaded.
  // Patches every loaded page that happens to hold this doc (not just the
  // current tag's), matching the hook's own "no list-wide refetch needed"
  // contract: flipping this flag never changes tag membership or counts.
  const patchDocRetrievable = (documentUid: string, retrievable: boolean) => {
    setPerTag((prev) => {
      const next: typeof prev = {};
      for (const [tagId, page] of Object.entries(prev)) {
        next[tagId] = {
          ...page,
          docs: page.docs.map((d) =>
            d.identity.document_uid === documentUid ? { ...d, source: { ...d.source, retrievable } } : d,
          ),
        };
      }
      return next;
    });
  };

  const toggleSearchable = async (doc: DocumentMetadata) => {
    const next = await commands.toggleRetrievable(doc);
    if (next !== undefined) patchDocRetrievable(doc.identity.document_uid, next);
  };

  // Same rationale as patchDocRetrievable above: a label add/remove never
  // changes tag membership or counts, so patch every loaded page holding this
  // doc instead of a list-wide refetch.
  const patchDocLabels = (documentUid: string, labels: string[]) => {
    setPerTag((prev) => {
      const next: typeof prev = {};
      for (const [tagId, page] of Object.entries(prev)) {
        next[tagId] = {
          ...page,
          docs: page.docs.map((d) => (d.identity.document_uid === documentUid ? { ...d, labels } : d)),
        };
      }
      return next;
    });
  };

  const bulkToggleSearchable = async () => {
    // searchToggleMode being defined guarantees the toggle-relevant subset of
    // the selection is uniform (all searchable or all excluded), so toggling
    // every one of those docs unconditionally moves them all the same
    // direction. Tabular-only docs are skipped — same reasoning as
    // searchToggleMode above, they were never counted toward that direction.
    await Promise.all(selectedDocs.filter((doc) => !isTabularOnlyDoc(doc)).map((doc) => toggleSearchable(doc)));
    setSelectedKeys(new Set());
  };

  // Non-destructive and repeatable — unlike delete/exclude above, the
  // selection is left as-is afterward (a user may well want to act on the
  // same rows again right after downloading them).
  const [bulkDownloading, setBulkDownloading] = useState(false);
  const bulkDownload = async () => {
    setBulkDownloading(true);
    try {
      await downloadManyAsZip(
        selectedDocs.map((doc) => ({
          filename: doc.identity.document_name || doc.identity.document_uid,
          fetchBlob: () => commands.fetchBlob(doc),
        })),
        "resources.zip",
      );
    } catch (e: unknown) {
      showError?.({
        summary: t("validation.error"),
        detail: (e as { data?: { detail?: string } })?.data?.detail || t("rework.resources.toast.downloadError"),
      });
    } finally {
      setBulkDownloading(false);
    }
  };

  const moreOptionsForFolder = (node: TagNode): OptionModel<"rename" | "delete">[] => {
    if (!canCreateFolder || !node.tagsHere[0]) return [];
    return [
      {
        value: "rename",
        key: "rename",
        label: t("rework.resources.action.rename"),
        icon: { category: "outlined", type: "drive_file_rename_outline" },
      },
      {
        value: "delete",
        key: "delete",
        label: t("rework.resources.action.delete"),
        icon: { category: "outlined", type: "delete" },
        destructive: true,
      },
    ];
  };

  const moreOptionsForDoc = (doc: DocumentMetadata): OptionModel<DocMenuAction>[] => {
    // Already ingested (`ready`) → "Retraiter": this re-runs the pipeline on a
    // document that already succeeded, not a first ingestion. Any other status
    // (raw/processing/failed) keeps "Traiter" — it hasn't been ingested yet.
    const status = getDocStatus(doc);
    const activeTask = activeDocTaskByUid.get(doc.identity.document_uid);
    const options: OptionModel<DocMenuAction>[] = [];
    // No "error detail" entry here: the per-stage messages ride the "failed"
    // StatusChip itself, on hover (#2315).
    if (canCreateFolder) {
      options.push({
        value: "rename",
        key: "rename",
        label: t("rework.resources.action.rename"),
        icon: { category: "outlined", type: "drive_file_rename_outline" },
      });
    }
    // Download is read-only — offered regardless of canCreateFolder, unlike
    // the three mutating actions around it.
    options.push({
      value: "download",
      key: "download",
      label: t("rework.resources.action.download"),
      icon: { category: "outlined", type: "download" },
    });
    if (canCreateFolder) {
      // Labels are descriptive metadata, not resource management — only
      // checks the document's own UPDATE access server-side, same gate as
      // rename, so it's offered under this same condition.
      options.push({
        value: "labels",
        key: "labels",
        label: t("rework.resources.action.manageLabels"),
        icon: { category: "outlined", type: "category" },
      });
      const excludedFromSearch = doc.source.retrievable === false;
      // A tabular-only dataset's `retrievable` is always false without being a
      // real exclusion (see isTabularOnlyDoc) — it stays queryable via the
      // SQL/tabular tool regardless. Offering "Include in search" here would
      // let a user flip `retrievable` to true on a doc with zero vector
      // chunks, which the ingestion invariant relies on never happening,
      // for zero actual benefit (there's nothing to include it into).
      options.push(
        ...(isTabularOnlyDoc(doc)
          ? []
          : [
              {
                value: "searchable" as const,
                key: "searchable",
                label: t(
                  excludedFromSearch ? "rework.resources.action.includeInSearch" : "rework.resources.action.searchable",
                ),
                icon: {
                  category: "outlined" as const,
                  type: excludedFromSearch ? ("search" as const) : ("search_off" as const),
                },
              },
            ]),
        ...(SHOW_REPROCESS_ACTION
          ? [
              {
                value: "process" as const,
                key: "process",
                label: t(status === "ready" ? "rework.resources.action.reprocess" : "rework.resources.action.process"),
                icon: { category: "outlined" as const, type: "refresh" as const },
              },
            ]
          : []),
        // Only while the backing task is genuinely stoppable — `cancelling`
        // means a stop was already requested, offering a second one is noise.
        ...(activeTask && (activeTask.state === "pending" || activeTask.state === "running")
          ? [
              {
                value: "stopIngestion" as const,
                key: "stopIngestion",
                label: t("rework.resources.action.stopIngestion"),
                icon: { category: "outlined" as const, type: "stop" as const },
                destructive: true,
              },
            ]
          : []),
        {
          value: "delete",
          key: "delete",
          label: t("rework.resources.action.delete"),
          icon: { category: "outlined", type: "delete" },
          destructive: true,
          // #2315: while an ingestion is live, "stop" is the only exit — it
          // cancels the workflow AND deletes the half-built document. A plain
          // delete here would race the still-running workflow, which can
          // re-write metadata/vectors right after the delete lands. Greyed
          // with a hover tooltip explaining why, per developer request.
          disabled: !!activeTask,
          ...(activeTask ? { tooltip: t("rework.resources.action.deleteDisabledWhileProcessing") } : {}),
        },
      );
    }
    return options;
  };

  const columns: DataTableColumn<Row>[] = [
    {
      label: t("rework.resources.columns.name"),
      size: "2fr",
      cellRenderer: (row) => {
        if (row.kind === "folder") {
          return (
            <button
              type="button"
              className={styles.nameButton}
              onClick={() => navigateTo(row.node.full)}
              {...folderDropProps(row.node, canCreateFolder)}
            >
              <span className={styles.rowIcon} style={{ color: FOLDER_ICON.color }}>
                <Icon category="outlined" type={FOLDER_ICON.type} filled={FOLDER_ICON.filled} />
              </span>
              <span>{row.node.name}</span>
            </button>
          );
        }
        const spec = fileIconSpec(row.doc.file?.file_type);
        const title = embeddedTitle(row.doc);
        return (
          <span className={styles.nameCell}>
            <span className={styles.rowIcon} style={{ color: spec.color }}>
              <Icon category="outlined" type={spec.type} filled={spec.filled} />
            </span>
            <span>{documentDisplayName(row.doc)}</span>
            {title && (
              <span className={styles.titleHintWrapper}>
                <Tooltip text={t("rework.resources.embeddedTitleHint", { title })}>
                  <span
                    className={styles.titleHintIcon}
                    tabIndex={0}
                    aria-label={t("rework.resources.embeddedTitleHint", { title })}
                  >
                    <Icon category="outlined" type="info" />
                  </span>
                </Tooltip>
              </span>
            )}
          </span>
        );
      },
    },
    {
      label: t("rework.resources.columns.size"),
      size: "6.5rem",
      cellRenderer: (row) => {
        if (row.kind === "folder") {
          const ids = folderDescendantTagIds.get(row.node.full) ?? [];
          const resolved = ids.length > 0 && ids.every((id) => folderSizes[id] !== undefined);
          const bytes = resolved ? ids.reduce((sum, id) => sum + (folderSizes[id] ?? 0), 0) : undefined;
          return <span className={styles.nowrapCell}>{bytes === undefined ? "—" : formatBytes(bytes)}</span>;
        }
        return <span className={styles.nowrapCell}>{formatBytes(row.doc.file?.file_size_bytes ?? 0)}</span>;
      },
    },
    {
      // Documents: source.date_added_to_kb, not identity.created — the
      // latter is the file's OWN embedded metadata (e.g. a .docx's core
      // "created" property, or nothing at all for a PDF, since that
      // processor never extracts one), not when it landed in Fred.
      // date_added_to_kb is stamped server-side at ingestion (SourceInfo's
      // Pydantic default_factory, base_input_processor.py) and always set.
      label: t("rework.resources.columns.created"),
      size: "9rem",
      cellRenderer: (row) => (
        <span className={styles.nowrapCell}>
          {formatDateTime(row.kind === "folder" ? row.node.tagsHere[0]?.created_at : row.doc.source.date_added_to_kb)}
        </span>
      ),
    },
    {
      // identity.author is the file's own embedded-metadata author, not the
      // Fred user who uploaded it — RFC §13.10 decision 10 / FRONT-09.L.
      // uploaded_by (the uid, stamped once at ingestion) is resolved to a
      // display name via the batched uploaderById lookup above; a document
      // ingested before this field existed has no uploaded_by and renders
      // "—", same as a folder (folders have no uploader concept at all).
      label: t("rework.resources.columns.author"),
      size: "9rem",
      cellRenderer: (row) => {
        const uid = row.kind === "document" ? row.doc.identity.uploaded_by : null;
        if (!uid) return <span className={styles.nowrapCell}>—</span>;
        const summary = uploaderById.get(uid);
        // A doc just uploaded this session adds a brand-new uid to
        // uploaderUids above, which re-keys the batched query and starts a
        // fresh fetch — until it resolves, `summary` is genuinely absent yet,
        // not "no such user". Falling through to userDisplayName's raw-uid
        // fallback here would flash the uploader's UUID for that window
        // instead of their name; "—" that self-corrects on the next render
        // reads as loading rather than as broken data.
        if (!summary && isFetchingUploaders) return <span className={styles.nowrapCell}>—</span>;
        return <span className={styles.nowrapCell}>{userDisplayName(uid, summary)}</span>;
      },
    },
    {
      // Fixed for the same header/body dual-grid reason as the actions column
      // below. Sized for the widest chip — FR "Traitement..." with its spinner
      // (~100px) — which 6rem clipped; the shorter Erreur/En attente chips
      // masked that until the live-task wiring (#2315) made "processing"
      // actually render here.
      label: "",
      size: "8rem",
      cellRenderer: (row) => {
        // A folder only ever shows "processing" (see ingestingFolders) — never
        // ready/raw/failed, which stay per-document states.
        if (row.kind === "folder") {
          return ingestingFolders.has(row.node.full) ? <StatusChip status="processing" /> : null;
        }
        return (
          <StatusChip
            status={getDocStatus(row.doc)}
            errors={row.doc.processing?.errors}
            justCompleted={justCompletedDocUids.has(row.doc.identity.document_uid)}
          />
        );
      },
    },
    {
      // Fixed, not "auto": DataTable renders the header and body as two
      // independent grids (RFC-tracked, for the scroll-starts-below-header
      // behavior), so an "auto" track sizes itself from each grid's OWN
      // content — the header's empty label vs. the row's icon buttons — and
      // the two grids disagree on this column's width. That leftover space
      // then gets absorbed differently by the flexible Name (2fr) column in
      // each grid, shifting every column after it out of alignment. A fixed
      // width both grids agree on avoids the whole class of drift. Sized for
      // up to three 2rem elements (the excluded-from-search indicator +
      // preview + the "more" trigger, the indicator only present on an
      // excluded document) + their gaps + the cell's own horizontal padding,
      // plus headroom.
      label: "",
      size: "8rem",
      cellRenderer: (row) => {
        // retrievable stays false for the entire ingestion window (it only
        // flips true once vectorization completes), not just for a deliberate
        // exclusion — gate on `ready` too, or this icon flags every
        // still-processing document as "excluded from search".
        const status = row.kind === "document" && getDocStatus(row.doc);
        return (
          <span className={styles.actionsCell}>
            {row.kind === "document" &&
              status === "ready" &&
              row.doc.source.retrievable === false &&
              !isTabularOnlyDoc(row.doc) && (
                <Tooltip text={t("rework.resources.status.excludedFromSearch")}>
                  <span className={styles.excludedIcon} aria-label={t("rework.resources.status.excludedFromSearch")}>
                    <Icon category="outlined" type="search_off" />
                  </span>
                </Tooltip>
              )}
            {row.kind === "document" && (
              <Tooltip text={t("rework.resources.action.preview")}>
                <IconButton
                  color="on-surface-retreat"
                  variant="icon"
                  size="small"
                  icon={{ category: "outlined", type: "visibility" }}
                  aria-label={t("rework.resources.action.preview")}
                  onClick={() => commands.preview(row.doc)}
                />
              </Tooltip>
            )}
            <IconButtonMenu<DocMenuAction>
              iconButton={{
                color: "on-surface-retreat",
                variant: "icon",
                size: "small",
                icon: { category: "outlined", type: "more_vert" },
                "aria-label": t("rework.resources.action.more"),
              }}
              options={row.kind === "folder" ? moreOptionsForFolder(row.node) : moreOptionsForDoc(row.doc)}
              onSelect={(value) => {
                if (row.kind === "folder") {
                  if (value === "rename") setRenameTarget({ kind: "folder", node: row.node });
                  if (value === "delete") void confirmDeleteFolder(row.node);
                } else {
                  if (value === "rename") setRenameTarget({ kind: "document", doc: row.doc });
                  if (value === "download") void commands.download(row.doc);
                  if (value === "labels") setLabelsTarget(row.doc);
                  if (value === "searchable") void toggleSearchable(row.doc);
                  if (value === "process" && currentTag) void reprocess(row.doc, currentTag.id);
                  if (value === "stopIngestion") confirmStopIngestion(row.doc);
                  if (value === "delete" && currentTag) {
                    showConfirmationDialog({
                      title: t("rework.resources.confirm.deleteTitle"),
                      message: t("rework.resources.confirm.deleteMessage", {
                        name: documentDisplayName(row.doc),
                      }),
                      onConfirm: () =>
                        void commands.removeFromLibrary(row.doc, currentTag as unknown as TagWithItemsId),
                    });
                  }
                }
              }}
            />
          </span>
        );
      },
    },
  ];

  const breadcrumbSegments = useMemo(() => {
    const rootLabel = t("rework.resources.roots.resources");
    if (!currentFolderFull) return [{ label: rootLabel }];
    const parts = currentFolderFull.split("/");
    const segments = [{ label: rootLabel, onClick: () => navigateTo(null) }];
    let acc = "";
    parts.forEach((part, i) => {
      acc = acc ? `${acc}/${part}` : part;
      // Snapshot this iteration's path: every segment's onClick otherwise
      // closes over the same mutable `acc` binding, so by the time any of
      // them actually fires (a later click), they'd all navigate to
      // whatever `acc` was left at after the loop finished — the deepest
      // folder — instead of the segment that was actually clicked.
      const stepPath = acc;
      const isLast = i === parts.length - 1;
      segments.push({ label: part, onClick: isLast ? undefined : () => navigateTo(stepPath) });
    });
    return segments;
  }, [currentFolderFull, t, navigateTo]);

  const isEmpty = !tagsLoading && !page?.loading && childFolders.length === 0 && (page?.docs.length ?? 0) === 0;

  // The upload drawer targets whichever folder triggered it: a drop target
  // (dropTargetNode) when opened by dragging files onto a folder row, or the
  // currently-viewed folder for the toolbar's "+"/manual upload.
  const uploadTargetNode = dropTargetNode ?? currentNode;
  const uploadTargetTag = uploadTargetNode.tagsHere[0] ?? null;

  // Walks/creates the tag chain for one dropped subdirectory under the upload
  // target, returning the leaf's tag id — how a dropped folder keeps its
  // on-disk structure as nested tags (the drawer calls this once per distinct
  // subdirectory before uploading). Existing levels are resolved from the
  // loaded tree or the pendingFolderTagIds cache; missing ones are created
  // like CreateFolderModal would (same TagCreate shape). A 409 means the tag
  // exists server-side but not in the loaded tree (stale list, concurrent
  // creation elsewhere) — refetch and read its id from the fresh list.
  const ensureFolderPath = useCallback(
    async (segments: string[]): Promise<string | null> => {
      let parentFull = uploadTargetNode.full;
      let parentNode: TagNode | null = uploadTargetNode;
      let tagId: string | null = uploadTargetNode.tagsHere[0]?.id ?? null;
      for (const segment of segments) {
        const full = parentFull ? `${parentFull}/${segment}` : segment;
        const node: TagNode | null = parentNode?.children.get(segment) ?? null;
        let id = pendingFolderTagIds.current.get(full) ?? node?.tagsHere[0]?.id ?? null;
        if (!id) {
          try {
            const created = await createTag({
              tagCreate: {
                name: segment,
                path: parentFull || null,
                type: "document",
                team_id: isPersonalTeam ? null : teamId,
              },
            }).unwrap();
            id = created.id;
          } catch (err) {
            if ((err as { status?: number | string })?.status === 409) {
              const fresh = await refetchTags().unwrap();
              id = (fresh ?? []).find((tag) => tag.type === "document" && fullPath(tag) === full)?.id ?? null;
            }
            if (!id) {
              const detail = (err as { data?: { detail?: string } })?.data?.detail;
              throw new Error(detail ?? t("rework.resources.folderModal.error"));
            }
          }
        }
        pendingFolderTagIds.current.set(full, id);
        parentFull = full;
        parentNode = node;
        tagId = id;
      }
      return tagId;
    },
    [uploadTargetNode, createTag, isPersonalTeam, teamId, refetchTags, t],
  );

  // The full page is a drop surface for the folder being viewed — the drill-down
  // model shows one folder at a time, so "drop anywhere" reads as "add to this
  // folder". Folder rows keep their own (more specific) drop target above this
  // one. Same CAN_UPDATE_RESOURCES gate as the toolbar upload action. At the
  // corpus root there is no tag to attach plain files to, so only dropped
  // FOLDERS are accepted there — each one becomes a library mirroring its
  // structure (openDrawerWithDroppedFiles filters loose files out).
  const atRoot = !currentFolderFull;
  const pageDroppable = canCreateFolder && (!!currentTag || atRoot);
  const pageDropProps = pageDroppable
    ? {
        onDragOver: (event: React.DragEvent) => {
          if (!isFileDrag(event)) return;
          event.preventDefault();
          event.dataTransfer.dropEffect = "copy";
        },
        onDragEnter: (event: React.DragEvent) => {
          if (!isFileDrag(event)) return;
          setPageDragOver(true);
        },
        onDragLeave: (event: React.DragEvent) => {
          if (event.currentTarget.contains(event.relatedTarget as Node | null)) return;
          setPageDragOver(false);
        },
        onDrop: (event: React.DragEvent) => {
          setPageDragOver(false);
          openDrawerWithDroppedFiles(event, currentNode, atRoot);
        },
      }
    : {};
  const pageDragActive = pageDroppable && pageDragOver && !dragOverFolder;

  return (
    <div className={styles.workspace} data-page-drag-over={pageDragActive || undefined} {...pageDropProps}>
      <ResourceExplorer<Row>
        breadcrumb={{
          segments: breadcrumbSegments,
          onBack: navigateBack,
          canGoBack: !!currentFolderFull,
          backLabel: t("rework.resources.action.back"),
        }}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: t("rework.resources.search.placeholder"),
          ariaLabel: t("rework.resources.search.ariaLabel"),
          clearAriaLabel: t("rework.resources.search.clearAriaLabel"),
        }}
        toolbarActions={
          selectedDocs.length > 0 ? (
            <BulkActionsBar
              selectedCount={selectedDocs.length}
              onDelete={bulkDelete}
              onClearSelection={() => setSelectedKeys(new Set())}
              searchToggle={searchToggleMode ? { mode: searchToggleMode, onClick: bulkToggleSearchable } : undefined}
              onDownload={() => void bulkDownload()}
              downloadLoading={bulkDownloading}
            />
          ) : (
            canCreateFolder && (
              <>
                <Tooltip text={t("rework.resources.menu.newFolder")}>
                  <IconButton
                    color="primary"
                    variant="icon"
                    size="medium"
                    icon={{ category: "outlined", type: "create_new_folder" }}
                    aria-label={t("rework.resources.menu.newFolder")}
                    onClick={() => setCreateOpen(true)}
                  />
                </Tooltip>
                <Tooltip
                  text={currentTag ? t("rework.resources.action.addFile") : t("rework.resources.action.addFileHint")}
                >
                  <IconButton
                    color="primary"
                    variant="icon"
                    size="medium"
                    icon={{ category: "outlined", type: "upload_file" }}
                    aria-label={t("rework.resources.action.addFile")}
                    disabled={!currentTag}
                    onClick={() => setUploadOpen(true)}
                  />
                </Tooltip>
              </>
            )
          )
        }
        loading={tagsLoading}
        loadingMessage={t("rework.resources.loading")}
        empty={isEmpty}
        emptyMessage={
          currentFolderFull ? t("rework.resources.empty.folder") : t("rework.resources.empty.createLibrary")
        }
        columns={columns}
        rows={filteredRows}
        rowKey={rowKey}
        selectedKeys={selectedKeys}
        onSelectedKeysChange={setSelectedKeys}
        serverPagination={
          currentTag
            ? {
                totalCount: page?.total ?? 0,
                offset: page?.offset ?? 0,
                limit: rowsPerPage,
                onOffsetChange: (offset) => void loadTagPage(currentTag.id, offset),
                onLimitChange: handleRowsPerPageChange,
              }
            : undefined
        }
      />

      {pageDragActive && (
        <div className={styles.pageDropOverlay} aria-hidden>
          <Icon category="outlined" type="upload" />
          <span>
            {atRoot
              ? t("rework.resources.dropAtRoot")
              : t("rework.resources.dropInFolder", { folder: currentNode.name })}
          </span>
        </div>
      )}

      <InlineDrawer
        open={!!commands.previewTarget}
        onClose={commands.closePreview}
        title={commands.previewTarget?.fileName ?? t("rework.resources.preview.title")}
        width="80vw"
        background="var(--surface-container-high)"
        headerActions={
          isPdfFile(commands.previewTarget?.fileName) ? (
            <DocumentViewerModeToggle view={previewView} onChange={setPreviewView} />
          ) : undefined
        }
      >
        {commands.previewTarget && (
          <DocumentViewer
            documentUid={commands.previewTarget.documentUid}
            fileName={commands.previewTarget.fileName}
            view={previewView}
          />
        )}
      </InlineDrawer>
      <DocumentUploadDrawer
        isOpen={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          setDroppedFiles(undefined);
          setDropTargetNode(null);
          pendingFolderTagIds.current.clear();
        }}
        initialFiles={droppedFiles}
        teamId={teamId}
        destinationPath={uploadTargetNode.full || undefined}
        metadata={{ tags: uploadTargetTag ? [uploadTargetTag.id] : [] }}
        ensureFolderPath={canCreateFolder ? ensureFolderPath : undefined}
        requireFolderPerFile={!uploadTargetTag}
        onUploadComplete={() => {
          if (uploadTargetTag) void loadTagPage(uploadTargetTag.id, perTag[uploadTargetTag.id]?.offset ?? 0);
          void refetchTags();
        }}
      />
      <CreateFolderModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        parentPath={currentFolderFull ?? undefined}
        teamId={isPersonalTeam ? undefined : teamId}
        onCreated={() => void refetchTags()}
      />
      {renameTarget && (
        <RenameModal
          open={!!renameTarget}
          onClose={() => setRenameTarget(null)}
          initialName={renameTarget.kind === "folder" ? renameTarget.node.name : documentDisplayName(renameTarget.doc)}
          lockedSuffix={renameTarget.kind === "document" ? documentExtension(renameTarget.doc) : undefined}
          onSubmit={async (newName) => {
            if (renameTarget.kind === "folder") {
              const tag = renameTarget.node.tagsHere[0];
              if (tag) await commands.renameTag(tag as unknown as TagWithItemsId, newName);
            } else {
              await commands.renameDocument(renameTarget.doc, newName);
            }
          }}
        />
      )}
      {labelsTarget && (
        <ManageLabelsModal
          open={!!labelsTarget}
          onClose={() => setLabelsTarget(null)}
          doc={labelsTarget}
          onMutate={async (patch) => {
            const next = await commands.mutateLabels(labelsTarget, patch);
            if (next) patchDocLabels(labelsTarget.identity.document_uid, next);
            return next;
          }}
        />
      )}
    </div>
  );
}

export default DocumentWorkspace;
