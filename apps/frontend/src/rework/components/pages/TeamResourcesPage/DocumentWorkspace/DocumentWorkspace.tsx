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

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useState } from "react";
import { fromEvent } from "file-selector";
import { useTranslation } from "react-i18next";
import { useSelector } from "react-redux";
import { Breadcrumb } from "@shared/molecules/Breadcrumb/Breadcrumb.tsx";
import DataTable, { type DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { IconType } from "@shared/utils/Type.ts";
import type { OptionModel } from "@models/Option.model.ts";
import { DocumentUploadDrawer } from "@shared/organisms/DocumentUploadDrawer/DocumentUploadDrawer.tsx";
import { DocumentViewer } from "@shared/organisms/DocumentViewer/DocumentViewer.tsx";
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
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { buildTree, findNode, type TagNode } from "../../../../../shared/utils/tagTree.ts";
import { selectActiveTasks } from "../../../../features/tasks/taskSlice";
import { useRefetchOnTaskSuccess } from "../../../../features/tasks/useRefetchOnTaskSuccess";
import { useNotifyOnNewTaskTarget } from "../../../../features/tasks/useNotifyOnNewTaskTarget";
import { useDocumentCommands } from "../../../../../components/documents/common/useDocumentCommands";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useGetTeamQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import { formatBytes } from "../../../../utils/formatBytes.ts";
import { formatDateTime } from "../../../../utils/formatDateTime.ts";
import CreateFolderModal from "../CreateFolderModal/CreateFolderModal.tsx";
import RenameModal from "../RenameModal/RenameModal.tsx";
import { StatusChip } from "../StatusChip/StatusChip.tsx";
import BulkActionsBar from "../BulkActionsBar/BulkActionsBar.tsx";
import { deriveDocStatus } from "./deriveDocStatus.ts";
import { pagesToRefreshOnTaskCompletion } from "./refreshOnCompletion.ts";
import { ResourcePagination } from "./ResourcePagination/ResourcePagination.tsx";
import styles from "./DocumentWorkspace.module.css";

const PAGE_SIZE = 50;
// Port of main's DocumentLibraryList live-status loop: while a loaded row is
// processing, its folder page is reloaded on this cadence so the badge flips
// to Ready/Failed without a manual refresh.
const DOC_STATUS_POLL_MS = 3000;
// How long a just-reprocessed row stays pinned to "processing" when the
// backend never re-stamps its stages (dead worker, dropped workflow).
const REPROCESS_OVERRIDE_TTL_MS = 90_000;

const FILE_TYPE_ICON: Record<string, IconType> = {
  pdf: "picture_as_pdf",
  pptx: "slideshow",
  xlsx: "table_chart",
  csv: "table_chart",
};

interface PageState {
  docs: DocumentMetadata[];
  total: number;
  offset: number;
  loading: boolean;
}

interface DocumentWorkspaceProps {
  teamId: string;
  isPersonalTeam: boolean;
}

/** Imperative handle so the Resources root "+" can drive the corpus add actions. */
export interface DocumentWorkspaceHandle {
  openUpload: () => void;
  openNewFolder: () => void;
}

/** The "User Assets" tag is surfaced in its own tab, not in the folder tree. */
const isUserAssetsTag = (name: string, path?: string | null) => name === "User Assets" || path === "user-assets";

type Row = { kind: "folder"; node: TagNode } | { kind: "document"; doc: DocumentMetadata };

function rowKey(row: Row): string {
  return row.kind === "folder" ? `folder:${row.node.full}` : `doc:${row.doc.identity.document_uid}`;
}

/**
 * Corpus d'équipe tab (RFC §13, Resources dashboard v2): breadcrumb drill-down
 * through one library (tag) level at a time — replaces the pre-FRONT-09.G
 * always-expanded tree — with a `DataTable` of the current folder's direct
 * children (subfolders + documents). Heavy listing stays on the backend:
 * folders lazy-load their first document page on entry.
 */
const DocumentWorkspace = forwardRef<DocumentWorkspaceHandle, DocumentWorkspaceProps>(function DocumentWorkspace(
  { teamId, isPersonalTeam },
  ref,
) {
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
    refetch: refetchTags,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery({
    type: "document",
    ownerFilter,
    teamId: isPersonalTeam ? undefined : teamId,
    limit: 10000,
    offset: 0,
  });

  const tree = useMemo(() => {
    const documentTags = (tags ?? []).filter((tag) => !isUserAssetsTag(tag.name, tag.path));
    return buildTree(documentTags);
  }, [tags]);

  // null => at the Corpus root (the tree's synthetic top node).
  const [currentFolderFull, setCurrentFolderFull] = useState<string | null>(null);
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

  useImperativeHandle(
    ref,
    () => ({
      openUpload: () => setUploadOpen(true),
      openNewFolder: () => {
        if (canCreateFolder) setCreateOpen(true);
      },
    }),
    [canCreateFolder],
  );

  const [browseDocumentsByTag] = useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();
  const [processDocuments] = useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation();
  const [deleteTag] = useDeleteTagKnowledgeFlowV1TagsTagIdDeleteMutation();

  const currentNode = currentFolderFull ? findNode(tree, currentFolderFull) : tree;
  const currentTag = currentNode.tagsHere[0] ?? null;

  const loadTagPage = useCallback(
    async (tagId: string, offset: number) => {
      setPerTag((prev) => ({
        ...prev,
        [tagId]: { docs: prev[tagId]?.docs ?? [], total: prev[tagId]?.total ?? 0, offset, loading: true },
      }));
      try {
        const res = await browseDocumentsByTag({
          browseDocumentsByTagRequest: { tag_id: tagId, offset, limit: PAGE_SIZE },
        }).unwrap();
        setPerTag((prev) => ({
          ...prev,
          [tagId]: { docs: res.documents ?? [], total: res.total ?? 0, offset, loading: false },
        }));
      } catch {
        setPerTag((prev) => ({ ...prev, [tagId]: { ...prev[tagId], loading: false } as PageState }));
      }
    },
    [browseDocumentsByTag],
  );

  const navigateTo = useCallback((full: string | null) => {
    setCurrentFolderFull(full);
    setSelectedKeys(new Set());
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
  const rows: Row[] = useMemo(
    () => [
      ...childFolders.map((node): Row => ({ kind: "folder", node })),
      ...(page?.docs ?? []).map((doc): Row => ({ kind: "document", doc })),
    ],
    [childFolders, page?.docs],
  );

  const selectedDocs = useMemo(
    () =>
      rows
        .filter((row): row is Row & { kind: "document" } => row.kind === "document" && selectedKeys.has(rowKey(row)))
        .map((row) => row.doc),
    [rows, selectedKeys],
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

  const bulkExcludeFromSearch = () => {
    // Only flip docs that are currently searchable — toggling an already-excluded
    // one would re-include it, the opposite of "exclude from search".
    for (const doc of selectedDocs) if (doc.source.retrievable) void commands.toggleRetrievable(doc);
    setSelectedKeys(new Set());
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

  const moreOptionsForDoc = (): OptionModel<"rename" | "searchable" | "process" | "delete">[] => {
    if (!canCreateFolder) return [];
    return [
      {
        value: "rename",
        key: "rename",
        label: t("rework.resources.action.rename"),
        icon: { category: "outlined", type: "drive_file_rename_outline" },
      },
      {
        value: "searchable",
        key: "searchable",
        label: t("rework.resources.action.searchable"),
        icon: { category: "outlined", type: "search_off" },
      },
      {
        value: "process",
        key: "process",
        label: t("rework.resources.action.process"),
        icon: { category: "outlined", type: "refresh" },
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

  const columns: DataTableColumn<Row>[] = [
    {
      label: t("rework.resources.columns.name"),
      size: "3fr",
      cellRenderer: (row) =>
        row.kind === "folder" ? (
          <button
            type="button"
            className={styles.nameButton}
            onClick={() => navigateTo(row.node.full)}
            {...folderDropProps(row.node, canCreateFolder)}
          >
            <Icon category="outlined" type="folder" />
            <span>{row.node.name}</span>
          </button>
        ) : (
          <span className={styles.nameCell}>
            <Icon category="outlined" type={FILE_TYPE_ICON[row.doc.file?.file_type ?? ""] ?? "description"} />
            <span>{row.doc.identity.title || row.doc.identity.document_name}</span>
          </span>
        ),
    },
    {
      label: t("rework.resources.columns.size"),
      cellRenderer: (row) =>
        row.kind === "folder"
          ? t("rework.resources.folder.docCount", { count: row.node.tagsHere[0]?.item_ids?.length ?? 0 })
          : formatBytes(row.doc.file?.file_size_bytes ?? 0),
    },
    {
      label: t("rework.resources.columns.created"),
      cellRenderer: (row) =>
        formatDateTime(row.kind === "folder" ? row.node.tagsHere[0]?.created_at : row.doc.identity.created),
    },
    {
      label: t("rework.resources.columns.author"),
      cellRenderer: (row) => (row.kind === "document" ? (row.doc.identity.author ?? "—") : "—"),
    },
    {
      label: "",
      cellRenderer: (row) => {
        if (row.kind !== "document") return null;
        const status = reprocessOverrides[row.doc.identity.document_uid]
          ? "processing"
          : deriveDocStatus(row.doc).status;
        return <StatusChip status={status} />;
      },
    },
    {
      label: "",
      size: "auto",
      cellRenderer: (row) => (
        <span className={styles.actionsCell}>
          {row.kind === "document" && (
            <IconButton
              color="on-surface"
              variant="icon"
              size="small"
              icon={{ category: "outlined", type: "visibility" }}
              aria-label={t("rework.resources.action.preview")}
              title={t("rework.resources.action.preview")}
              onClick={() => commands.preview(row.doc)}
            />
          )}
          <IconButtonMenu<"rename" | "delete" | "searchable" | "process">
            iconButton={{
              color: "on-surface",
              variant: "icon",
              size: "small",
              icon: { category: "outlined", type: "more_vert" },
              "aria-label": t("rework.resources.action.more"),
            }}
            options={row.kind === "folder" ? moreOptionsForFolder(row.node) : moreOptionsForDoc()}
            onSelect={(value) => {
              if (row.kind === "folder") {
                if (value === "rename") setRenameTarget({ kind: "folder", node: row.node });
                if (value === "delete") confirmDeleteFolder(row.node);
              } else {
                if (value === "rename") setRenameTarget({ kind: "document", doc: row.doc });
                if (value === "searchable") void commands.toggleRetrievable(row.doc);
                if (value === "process" && currentTag) void reprocess(row.doc, currentTag.id);
                if (value === "delete" && currentTag) {
                  showConfirmationDialog({
                    title: t("rework.resources.confirm.deleteTitle"),
                    message: t("rework.resources.confirm.deleteMessage", {
                      name: row.doc.identity.title || row.doc.identity.document_name,
                    }),
                    onConfirm: () => void commands.removeFromLibrary(row.doc, currentTag as unknown as TagWithItemsId),
                  });
                }
              }
            }}
          />
        </span>
      ),
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
      const isLast = i === parts.length - 1;
      segments.push({ label: part, onClick: isLast ? undefined : () => navigateTo(acc) });
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
      <div className={styles.toolbar}>
        <Breadcrumb segments={breadcrumbSegments} />
        <span className={styles.toolbarEnd}>
          <BulkActionsBar
            selectedCount={selectedDocs.length}
            onDelete={bulkDelete}
            onExcludeFromSearch={bulkExcludeFromSearch}
          />
          {canCreateFolder && (
            <>
              <IconButton
                color="on-surface"
                variant="outlined"
                size="small"
                icon={{ category: "outlined", type: "create_new_folder" }}
                aria-label={t("rework.resources.menu.newFolder")}
                title={t("rework.resources.menu.newFolder")}
                onClick={() => setCreateOpen(true)}
              />
              <IconButton
                color="on-surface"
                variant="outlined"
                size="small"
                icon={{ category: "outlined", type: "upload" }}
                aria-label={t("rework.resources.action.addFile")}
                title={currentTag ? t("rework.resources.action.addFile") : t("rework.resources.action.addFileHint")}
                disabled={!currentTag}
                onClick={() => setUploadOpen(true)}
              />
            </>
          )}
        </span>
      </div>

      {tagsLoading ? (
        <div className={styles.hint}>{t("rework.resources.loading")}</div>
      ) : isEmpty ? (
        <div className={styles.hint}>
          {currentFolderFull ? t("rework.resources.empty.folder") : t("rework.resources.empty.createLibrary")}
        </div>
      ) : (
        <DataTable<Row>
          columns={columns}
          data={rows}
          rowKey={rowKey}
          firstColumnInset
          selectable
          selectedKeys={selectedKeys}
          onSelectionChange={setSelectedKeys}
        />
      )}
      {page && page.total > PAGE_SIZE && currentTag && (
        <ResourcePagination
          offset={page.offset}
          limit={PAGE_SIZE}
          total={page.total}
          onPrev={() => void loadTagPage(currentTag.id, Math.max(0, page.offset - PAGE_SIZE))}
          onNext={() => void loadTagPage(currentTag.id, page.offset + PAGE_SIZE)}
        />
      )}

      <InlineDrawer
        open={!!commands.previewTarget}
        onClose={commands.closePreview}
        title={commands.previewTarget?.fileName ?? t("rework.resources.preview.title")}
        width="80vw"
      >
        {commands.previewTarget && (
          <DocumentViewer
            documentUid={commands.previewTarget.documentUid}
            fileName={commands.previewTarget.fileName}
            showRawToggle
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
          initialName={
            renameTarget.kind === "folder"
              ? renameTarget.node.name
              : renameTarget.doc.identity.title || renameTarget.doc.identity.document_name
          }
          onSubmit={async (newName) => {
            if (renameTarget.kind === "folder") {
              const tag = renameTarget.node.tagsHere[0];
              if (tag) await commands.renameTag(tag as unknown as TagWithItemsId, newName);
            } else {
              await commands.renameDocumentTitle(renameTarget.doc, newName);
            }
          }}
        />
      )}
    </div>
  );
});

export default DocumentWorkspace;
