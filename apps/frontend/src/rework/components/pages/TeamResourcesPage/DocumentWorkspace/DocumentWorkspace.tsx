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
  useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation,
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { buildTree, collectDescendantTagIds, findNode, type TagNode } from "../../../../../shared/utils/tagTree.ts";
import { selectActiveTasks } from "../../../../features/tasks/taskSlice";
import { useRefetchOnTaskSuccess } from "../../../../features/tasks/useRefetchOnTaskSuccess";
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
import RenameModal from "../RenameModal/RenameModal.tsx";
import { StatusChip } from "../StatusChip/StatusChip.tsx";
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

function rowKey(row: Row): string {
  return row.kind === "folder" ? `folder:${row.node.full}` : `doc:${row.doc.identity.document_uid}`;
}

// identity.title (decision 9, RFC §13.8: cosmetic in-app rename) never carries
// an extension — it's either a plain user-typed label, or, for a never-renamed
// document, the file's own embedded "title" metadata property (e.g. a pptx's
// core Title, commonly auto-filled by PowerPoint from the template/first
// slide and never including ".pptx"). identity.document_name always does
// ("Original file name incl. extension"), so it's the source of truth for the
// extension regardless of which label wins for display.
// Matches the backend's own extension check (Path(name).suffix) in
// rename_document — a rename may never change it (DOCUMENT-RENAME-RFC.md §4).
function documentExtension(doc: DocumentMetadata): string {
  const dot = doc.identity.document_name.lastIndexOf(".");
  return dot > 0 ? doc.identity.document_name.slice(dot) : "";
}

function documentDisplayName(doc: DocumentMetadata): string {
  const label = doc.identity.title || doc.identity.document_name;
  const extension = documentExtension(doc);
  return extension && !label.toLowerCase().endsWith(extension.toLowerCase()) ? `${label}${extension}` : label;
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
  const { showSuccess, showError } = useToast();
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
  const [selectedKeys, setSelectedKeys] = useState<ReadonlySet<string | number>>(new Set());
  const [renameTarget, setRenameTarget] = useState<
    { kind: "folder"; node: TagNode } | { kind: "document"; doc: DocumentMetadata } | null
  >(null);
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

  // Load the current folder's document page on entry (and once when its tag
  // first resolves) — mirrors the old "load on expand" behavior, now scoped
  // to whichever single folder is being viewed.
  useEffect(() => {
    if (currentTag && !perTag[currentTag.id]) void loadTagPage(currentTag.id, 0);
  }, [currentTag, perTag, loadTagPage]);

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
  useEffect(() => {
    const pendingTagIds = Object.entries(perTag)
      .filter(([, page]) =>
        page.docs.some(
          (doc) =>
            deriveDocStatus(doc).status === "processing" || reprocessOverrides[doc.identity.document_uid] !== undefined,
        ),
      )
      .map(([tagId]) => tagId);
    if (pendingTagIds.length === 0) return;
    const interval = setInterval(() => {
      for (const tagId of pendingTagIds) void loadTagPage(tagId, perTag[tagId]?.offset ?? 0);
    }, DOC_STATUS_POLL_MS);
    return () => clearInterval(interval);
  }, [perTag, reprocessOverrides, loadTagPage]);

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

  // When an ingestion task finishes, the browse snapshot that backs its row is
  // stale (still "raw") and would need a manual refresh to show "Ready". Reload
  // just the loaded folder page(s) showing that document so its status goes live.
  useRefetchOnTaskSuccess("document", (documentUid) => {
    for (const [tagId, page] of Object.entries(perTag)) {
      if (page.docs.some((doc) => doc.identity.document_uid === documentUid)) {
        void loadTagPage(tagId, page.offset);
      }
    }
  });

  // A brand-new document (just registered by the upload drawer) has no row
  // anywhere yet, so `useRefetchOnTaskSuccess` above can never trigger its first
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
  const confirmDeleteFolder = useCallback(
    (node: TagNode) => {
      const tag = node.tagsHere[0];
      if (!tag) return;
      const docCount = tag.item_ids?.length ?? 0;
      showConfirmationDialog({
        title: t("rework.resources.confirm.deleteFolderTitle"),
        message:
          docCount > 0
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
    [deleteTag, showConfirmationDialog, showSuccess, showError, t, refetchTags, currentFolderFull, navigateTo],
  );

  const runningDocIds = useMemo(
    () =>
      new Set(
        activeTasks
          .filter((task) => task.target?.type === "document" && task.state !== "failed")
          .map((task) => task.target?.id),
      ),
    [activeTasks],
  );

  const prevRunningDocIdsRef = useMemo(() => ({ current: new Set<string | undefined>() }), []);
  useEffect(() => {
    const pages = pagesToRefreshOnTaskCompletion(prevRunningDocIdsRef.current, runningDocIds, perTag);
    prevRunningDocIdsRef.current = runningDocIds;
    for (const { tagId, offset } of pages) void loadTagPage(tagId, offset);
  }, [runningDocIds, perTag, loadTagPage, prevRunningDocIdsRef]);

  /** OS-file drag-and-drop onto a folder row: pre-select that folder and open the
   * ingestion drawer seeded with the dropped files. Same gating as the row's
   * upload action. */
  const folderDropProps = (node: TagNode, droppable: boolean) => {
    if (!droppable) return {};
    const isFileDrag = (event: React.DragEvent) => event.dataTransfer.types.includes("Files");
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
        event.preventDefault();
        setDragOverFolder(null);
        // fromEvent must start synchronously: the DataTransfer entries needed to
        // walk a dropped directory are dead once the drop handler has returned.
        void fromEvent(event.nativeEvent).then((items) => {
          const dropped = items.filter((item): item is File => item instanceof File);
          if (dropped.length === 0) return;
          setDropTargetNode(node);
          setDroppedFiles(dropped);
          setUploadOpen(true);
        });
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

  const moreOptionsForDoc = (
    doc: DocumentMetadata,
  ): OptionModel<"rename" | "download" | "searchable" | "process" | "delete">[] => {
    // Already ingested (`ready`) → "Retraiter": this re-runs the pipeline on a
    // document that already succeeded, not a first ingestion. Any other status
    // (raw/processing/failed) keeps "Traiter" — it hasn't been ingested yet.
    const status = reprocessOverrides[doc.identity.document_uid] ? "processing" : deriveDocStatus(doc).status;
    const options: OptionModel<"rename" | "download" | "searchable" | "process" | "delete">[] = [];
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
        {
          value: "delete",
          key: "delete",
          label: t("rework.resources.action.delete"),
          icon: { category: "outlined", type: "delete" },
          destructive: true,
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
        return (
          <span className={styles.nameCell}>
            <span className={styles.rowIcon} style={{ color: spec.color }}>
              <Icon category="outlined" type={spec.type} filled={spec.filled} />
            </span>
            <span>{documentDisplayName(row.doc)}</span>
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
      label: "",
      size: "6rem",
      cellRenderer: (row) => {
        if (row.kind !== "document") return null;
        const status = reprocessOverrides[row.doc.identity.document_uid]
          ? "processing"
          : deriveDocStatus(row.doc).status;
        return <StatusChip status={status} />;
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
        const status =
          row.kind === "document" &&
          (reprocessOverrides[row.doc.identity.document_uid] ? "processing" : deriveDocStatus(row.doc).status);
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
            <IconButtonMenu<"rename" | "download" | "delete" | "searchable" | "process">
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
                  if (value === "delete") confirmDeleteFolder(row.node);
                } else {
                  if (value === "rename") setRenameTarget({ kind: "document", doc: row.doc });
                  if (value === "download") void commands.download(row.doc);
                  if (value === "searchable") void toggleSearchable(row.doc);
                  if (value === "process" && currentTag) void reprocess(row.doc, currentTag.id);
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

  return (
    <div className={styles.workspace}>
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
        }}
        initialFiles={droppedFiles}
        teamId={teamId}
        destinationPath={uploadTargetNode.full || undefined}
        metadata={{ tags: uploadTargetTag ? [uploadTargetTag.id] : [] }}
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
    </div>
  );
}

export default DocumentWorkspace;
