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
import { useRefetchOnWindowFocus } from "@core/hooks/crossSessionRefresh";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fromEvent } from "file-selector";
import { useTranslation } from "react-i18next";
import { useDispatch } from "react-redux";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import Select from "@shared/molecules/Select/Select";
import ResourceExplorer from "@shared/organisms/ResourceExplorer/ResourceExplorer.tsx";
import type { DataTableColumn, SortState } from "@shared/molecules/DataTable/DataTable.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { FOLDER_ICON } from "../../../../utils/fileIconSpec.ts";
import DocumentNameCell from "@shared/molecules/DocumentNameCell/DocumentNameCell.tsx";
import { documentDisplayName } from "@shared/molecules/DocumentNameCell/documentNaming.ts";
import { DocumentUploadDrawer } from "@shared/organisms/DocumentUploadDrawer/DocumentUploadDrawer.tsx";
import {
  MAX_FOLDER_DEPTH,
  exceedsMaxFolderDepth,
  folderPathDepth,
  relativeDirSegments,
} from "@shared/organisms/DocumentUploadDrawer/droppedPaths.ts";
import DocumentPreviewDrawer from "@shared/molecules/DocumentPreviewDrawer/DocumentPreviewDrawer.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { formatBytes } from "@shared/utils/formatBytes.ts";
import { formatDateTime } from "../../../../utils/formatDateTime.ts";
import CreateFolderModal from "../CreateFolderModal/CreateFolderModal.tsx";
import RenameModal from "../RenameModal/RenameModal.tsx";
import { StatusChip } from "@shared/molecules/StatusChip/StatusChip.tsx";
import type { DocStatus } from "@shared/atoms/DocStatusBadge/DocStatusBadge.tsx";
import BulkActionsBar from "../BulkActionsBar/BulkActionsBar.tsx";
import styles from "./DocumentWorkspace.module.css";
import {
  DEFAULT_ORDERING,
  SORTABLE_COLUMN_KEYS,
  orderingFromSortState,
  sortStateFromOrdering,
  type DocumentOrdering,
  type DocumentSortField,
} from "./documentOrdering.ts";
import { startManagerProcessing } from "../../../../features/imports/managerImportRun";
import {
  useSetRetrievableMutation,
  useEntriesQuery,
  useLazyEntriesQuery,
  useCreateFolderMutation,
  useRenameFolderMutation,
  useDeleteFolderMutation,
  useDeleteDocumentMutation,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import {
  presentManagerDocument,
  managerProcessingErrors,
  downloadManagerDocument,
  type ResourceDocument,
} from "../../../../features/imports/managerDocuments";
import type { Folder, Profile } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
type FolderNode = {
  name: string;
  full: string;
  managerFolder?: Folder;
};
const folderNode = (folder: Folder): FolderNode => ({ name: folder.name, full: folder.id, managerFolder: folder });
const DEFAULT_PAGE_SIZE = 50;
const DOC_STATUS_POLL_MS = 3000;
interface DocumentWorkspaceProps {
  teamId: string;
  managerSpaceId: string;
  /** The owning team's real id, when `teamId` is the "personal" URL alias.
   *  Only the import panel's scoping uses it; everywhere else `teamId` is
   *  already the real one. */
  importScopeId?: string;
  isPersonalTeam: boolean;
  /** Notified after any action that adds or removes a document (upload,
   * single/bulk removal, folder deletion) — lets the parent page's storage
   * stats cards (file count/size by type) refresh without owning any of
   * this workspace's own mutation plumbing. */
  onDocumentsChanged?: () => void;
}
type Row =
  | {
      kind: "folder";
      node: FolderNode;
    }
  | {
      kind: "document";
      doc: ResourceDocument;
    };
type DocMenuAction = "rename" | "download" | "searchable" | "relaunch" | "delete";
function rowKey(row: Row): string {
  return row.kind === "folder" ? `folder:${row.node.full}` : `doc:${row.doc.id}`;
}
/** An OS file drag (not a text/element drag) — shared by every drop surface. */
const isFileDrag = (event: React.DragEvent) => event.dataTransfer.types.includes("Files");
function DocumentWorkspace({ teamId, managerSpaceId, importScopeId, onDocumentsChanged }: DocumentWorkspaceProps) {
  const { t } = useTranslation();
  const dispatch = useDispatch();
  // One place the sortable columns get their label, shared by the column
  // definitions and by the sort-state translation both ways.
  const columnLabel = useCallback((field: DocumentSortField) => t(SORTABLE_COLUMN_KEYS[field]), [t]);
  const { showSuccess, showError, showWarn, showInfo } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const [currentFolderFull, setCurrentFolderFull] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [rowsPerPage, setRowsPerPage] = useState(DEFAULT_PAGE_SIZE);
  const [ordering, setOrdering] = useState<DocumentOrdering>(DEFAULT_ORDERING);
  const [folderOffset, setFolderOffset] = useState(0);
  const managerQuery = useEntriesQuery(
    {
      id: managerSpaceId ?? "",
      parentId: currentFolderFull ?? undefined,
      search,
      order: `${ordering.by}_${ordering.order}`,
      offset: folderOffset,
      limit: rowsPerPage,
    },
    {
      skip: !managerSpaceId,
      refetchOnMountOrArgChange: true,
    },
  );
  const failedManagerRead = useRef(false);
  if (managerQuery.isError) failedManagerRead.current = true;
  if (managerQuery.isSuccess && !managerQuery.isFetching) failedManagerRead.current = false;
  const directory = failedManagerRead.current ? undefined : managerQuery.currentData;
  useRefetchOnWindowFocus(managerQuery.refetch, !managerSpaceId);
  useEffect(() => {
    if (!managerSpaceId || managerQuery.isFetching || !directory) return;
    const active = Object.values(directory.processing ?? {}).some(
      (processing) => processing.status === "pending" || processing.status === "running",
    );
    const inclusionPending = directory.items.some(
      (entry) => entry.kind === "document" && entry.data.retrievable_pending,
    );
    if (!active && !inclusionPending) return;
    const timer = window.setTimeout(() => {
      if (document.visibilityState !== "hidden") void managerQuery.refetch();
    }, DOC_STATUS_POLL_MS);
    return () => window.clearTimeout(timer);
  }, [managerSpaceId, managerQuery.isFetching, managerQuery.refetch, directory]);
  const [findManagerEntries] = useLazyEntriesQuery();
  const [createManagerFolder] = useCreateFolderMutation();
  const [renameManagerFolder] = useRenameFolderMutation();
  const [deleteDocument] = useDeleteDocumentMutation();
  const [deleteManagerFolder] = useDeleteFolderMutation();
  const folderDeletions = useRef(new Map<string, Promise<unknown>>());
  const deleteManagerOnce = useCallback(
    (id: string) => {
      const existing = folderDeletions.current.get(id);
      if (existing) return existing;
      const request = deleteManagerFolder({ id }).unwrap();
      folderDeletions.current.set(id, request);
      void request.finally(() => folderDeletions.current.delete(id)).catch(() => {});
      return request;
    },
    [deleteManagerFolder],
  );
  // The explorer hides its table on an empty page, so its own pagination
  // cannot recover after the last row of the last page is removed.
  useEffect(() => {
    if (!directory) return;
    const last = Math.max(0, Math.ceil(directory.total / rowsPerPage) - 1) * rowsPerPage;
    if (folderOffset > last) {
      setFolderOffset(last);
      setSelectedKeys(new Set());
    }
  }, [directory, folderOffset, rowsPerPage]);
  const canCreateFolder = directory?.can_write === true;
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const currentFull = currentFolderFull;
  const [, setNavigationHistory] = useState<(string | null)[]>([]);
  const [selectedKeys, setSelectedKeys] = useState<ReadonlySet<string | number>>(new Set());
  const [renameTarget, setRenameTarget] = useState<FolderNode | null>(null);
  const relaunchRequests = useRef(new Set<string>());
  const [pendingRelaunches, setPendingRelaunches] = useState(new Set<string>());
  const [profilePromptOpen, setProfilePromptOpen] = useState(false);
  const [relaunchProfile, setRelaunchProfile] = useState<Profile>();
  const profileAnswer = useRef<((profile: Profile | undefined) => void) | null>(null);
  const answerProfile = (profile: Profile | undefined) => {
    setProfilePromptOpen(false);
    profileAnswer.current?.(profile);
    profileAnswer.current = null;
  };
  const getDocStatus = (doc: ResourceDocument): DocStatus | "stored" => {
    const status = doc.processing?.status;
    return status === "succeeded" ? "ready" : status === "failed" ? "failed" : status ? "processing" : "stored";
  };
  const isRelaunchable = (doc: ResourceDocument) =>
    !pendingRelaunches.has(doc.id) && (!doc.processing || doc.processing.status === "failed");
  const [uploadOpen, setUploadOpen] = useState(false);
  // Files dropped on a folder row, handed to the upload drawer as its initial list;
  // cleared on close so a later "+"-opened drawer starts empty.
  const [droppedFiles, setDroppedFiles] = useState<File[] | undefined>(undefined);
  const [dropTargetNode, setDropTargetNode] = useState<FolderNode | null>(null);
  const [dragOverFolder, setDragOverFolder] = useState<string | null>(null);
  // OS-file drag hovering anywhere over the opened folder's page (not a
  // specific folder row) — drives the full-page "drop here" overlay.
  const [pageDragOver, setPageDragOver] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [updateManagerRetrievable] = useSetRetrievableMutation();
  const currentFolder = directory?.ancestors[directory.ancestors.length - 1];
  const currentNode: FolderNode = currentFolder ? folderNode(currentFolder) : { name: "", full: "" };
  const childFolders = useMemo(
    () => (directory?.items ?? []).flatMap((entry) => (entry.kind === "folder" ? [folderNode(entry.data)] : [])),
    [directory],
  );
  const displayPath = directory?.ancestors.map((folder) => folder.name).join("/");
  const location = `${teamId}:${currentFull ?? ""}`;
  const locationRef = useRef(location);
  locationRef.current = location;
  const handleRowsPerPageChange = (limit: number) => {
    setRowsPerPage(limit);
    setFolderOffset(0);
    setSelectedKeys(new Set());
  };
  const handleSortChange = (next: SortState | null) => {
    setOrdering(orderingFromSortState(next, columnLabel));
    setFolderOffset(0);
    setSelectedKeys(new Set());
  };
  const [refreshing, setRefreshing] = useState(false);
  const refreshView = useCallback(async () => {
    setRefreshing(true);
    try {
      await managerQuery.refetch();
      return;
    } finally {
      setRefreshing(false);
    }
  }, [managerSpaceId, managerQuery]);
  const navigateTo = useCallback(
    (full: string | null) => {
      setNavigationHistory((prev) => [...prev, currentFolderFull]);
      setCurrentFolderFull(full);
      setFolderOffset(0);
      setSearch("");
      setCreateOpen(false);
      setRenameTarget(null);
      setUploadOpen(false);
      setSelectedKeys(new Set());
    },
    [currentFolderFull, managerSpaceId],
  );
  const navigateBack = useCallback(() => {
    setNavigationHistory((prev) => {
      if (prev.length === 0) return prev;
      setCurrentFolderFull(prev[prev.length - 1]);
      setFolderOffset(0);
      setSearch("");
      setCreateOpen(false);
      setRenameTarget(null);
      setUploadOpen(false);
      setSelectedKeys(new Set());
      return prev.slice(0, -1);
    });
  }, [managerSpaceId]);
  const [previewTarget, setPreviewTarget] = useState<{
    documentUid: string;
    fileName: string;
  } | null>(null);
  const setDocumentRetrievable = (doc: ResourceDocument, value: boolean) =>
    updateManagerRetrievable({ id: doc.id, setRetrievable: { retrievable: value } }).unwrap();
  const relaunchIngestion = useCallback(
    async (docs: ResourceDocument[]): Promise<boolean> => {
      if (docs.length === 0 || docs.some((doc) => relaunchRequests.current.has(doc.id))) return false;
      for (const doc of docs) relaunchRequests.current.add(doc.id);
      setPendingRelaunches(new Set(relaunchRequests.current));
      try {
        let selectedProfile: Profile | undefined;
        if (docs.some((doc) => !doc.processing?.profile)) {
          setRelaunchProfile(undefined);
          setProfilePromptOpen(true);
          selectedProfile = await new Promise<Profile | undefined>((resolve) => {
            profileAnswer.current = resolve;
          });
          if (!selectedProfile) return false;
        }
        try {
          for (const doc of docs)
            await startManagerProcessing(
              dispatch,
              doc.id,
              doc.processing?.profile ?? selectedProfile ?? "fast",
              doc.processing,
            );
          showSuccess?.({ summary: t("rework.resources.toast.relaunchStarted", { count: docs.length }) });
          return true;
        } catch (e: unknown) {
          showError?.({
            summary: t("validation.error"),
            detail:
              (
                e as {
                  data?: {
                    detail?: string;
                  };
                }
              )?.data?.detail ?? t("rework.resources.toast.relaunchError"),
          });
          return false;
        }
      } finally {
        for (const doc of docs) relaunchRequests.current.delete(doc.id);
        setPendingRelaunches(new Set(relaunchRequests.current));
      }
    },
    [dispatch, showSuccess, showError, t, managerSpaceId],
  );
  const confirmDeleteFolder = useCallback(
    async (node: FolderNode) => {
      if (node.managerFolder) {
        const id = node.managerFolder.id;
        showConfirmationDialog({
          title: t("rework.resources.confirm.deleteFolderTitle"),
          message: t("rework.resources.confirm.deleteManagerFolder", { name: node.name }),
          onConfirm: async () => {
            if (!mounted.current || locationRef.current !== location || folderDeletions.current.has(id)) return;
            try {
              await deleteManagerOnce(id);
              if (mounted.current && locationRef.current === location)
                showSuccess?.({ summary: t("rework.resources.toast.deleteFolderSuccess") });
            } catch (e) {
              if (mounted.current && locationRef.current === location)
                showError?.({
                  summary: t("validation.error"),
                  detail:
                    (
                      e as {
                        data?: {
                          detail?: string;
                        };
                      }
                    ).data?.detail ?? t("rework.resources.toast.deleteFolderError"),
                });
            }
          },
        });
        return;
      }
    },
    [deleteManagerOnce, location, showConfirmationDialog, showSuccess, showError, t],
  );
  /** Seed the ingestion drawer with an OS-file drop, targeting `node`.
   * `requireDir` (the corpus root, where a file can only live inside a
   * library): keep only files that came out of a dropped folder — their
   * chain becomes the library — and reject loose ones, with a toast. */
  const openDrawerWithDroppedFiles = (event: React.DragEvent, node: FolderNode, requireDir = false) => {
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
      const destinationDepth = folderPathDepth(node.managerFolder?.path);
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
  const folderDropProps = (node: FolderNode, droppable: boolean) => {
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
        setPageDragOver(false);
        openDrawerWithDroppedFiles(event, node);
      },
    };
  };
  const rows: Row[] = useMemo(
    () => [
      ...childFolders.map((node): Row => ({ kind: "folder", node })),
      ...(directory?.items ?? [])
        .flatMap((entry) =>
          entry.kind === "document" ? [presentManagerDocument(entry.data, directory?.processing?.[entry.data.id])] : [],
        )
        .map((doc): Row => ({ kind: "document", doc })),
    ],
    [childFolders, managerSpaceId, directory],
  );
  const filteredRows = rows;
  const selectedDocs = useMemo(
    () =>
      filteredRows
        .filter(
          (
            row,
          ): row is Row & {
            kind: "document";
          } => row.kind === "document" && selectedKeys.has(rowKey(row)),
        )
        .map((row) => row.doc),
    [filteredRows, selectedKeys],
  );
  const selectedFolders = useMemo(
    () =>
      filteredRows
        .filter(
          (
            row,
          ): row is Row & {
            kind: "folder";
          } => row.kind === "folder" && selectedKeys.has(rowKey(row)),
        )
        .map((row) => row.node),
    [filteredRows, selectedKeys],
  );
  const resolveFolderDocs = useCallback(
    async (
      folders: FolderNode[],
    ): Promise<
      {
        doc: ResourceDocument;
        relDir: string;
      }[]
    > => {
      const pending = folders.map((node) => ({ id: node.managerFolder!.id, relDir: node.name }));
      const visited = new Set<string>();
      const documents = new Map<
        string,
        {
          doc: ResourceDocument;
          relDir: string;
        }
      >();
      while (pending.length) {
        const folder = pending.pop()!;
        if (visited.has(folder.id)) continue;
        visited.add(folder.id);
        for (let offset = 0; ; ) {
          const page = await findManagerEntries({
            id: managerSpaceId,
            parentId: folder.id,
            offset,
            limit: 200,
          }).unwrap();
          for (const item of page.items) {
            if (item.kind === "folder")
              pending.push({ id: item.data.id, relDir: `${folder.relDir}/${item.data.name}` });
            else
              documents.set(item.data.id, {
                doc: presentManagerDocument(item.data, page.processing[item.data.id]),
                relDir: folder.relDir,
              });
          }
          offset += page.items.length;
          if (!page.items.length || offset >= page.total) break;
        }
      }
      return [...documents.values()];
    },
    [managerSpaceId, findManagerEntries],
  );
  const hasSelection = selectedDocs.length > 0 || selectedFolders.length > 0;
  // Unlike the search toggle there is no direction to disambiguate here, so a
  // mixed selection has one unambiguous meaning: relaunch the stuck ones, leave
  // the rest alone. Computed per render rather than memoized — it reads the
  // same live inputs as getDocStatus, and the selection is one page at most.
  // Selected FOLDERS are ignored: their descendants are not resolved.
  const relaunchableSelection = selectedDocs.filter(isRelaunchable);
  const [bulkRelaunching, setBulkRelaunching] = useState(false);
  const bulkRelaunch = async () => {
    if (relaunchableSelection.length === 0) return;
    setBulkRelaunching(true);
    try {
      if (await relaunchIngestion(relaunchableSelection)) setSelectedKeys(new Set());
    } finally {
      setBulkRelaunching(false);
    }
  };
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const managerBulkPending = useRef(false);
  const bulkDelete = () => {
    if (!hasSelection) return;
    showConfirmationDialog({
      title: t("rework.resources.action.delete"),
      message:
        selectedFolders.length === 0
          ? t("rework.resources.confirm.deleteManagerDocuments", { count: selectedDocs.length })
          : selectedDocs.length === 0
            ? t("rework.resources.confirm.deleteManagerFolders", { count: selectedFolders.length })
            : t("rework.resources.confirm.deleteManagerMixed", {
                folderCount: selectedFolders.length,
                docCount: selectedDocs.length,
              }),
      onConfirm: async () => {
        if (!mounted.current || locationRef.current !== location || managerBulkPending.current) return;
        managerBulkPending.current = true;
        setBulkDeleting(true);
        const outcomes = await Promise.allSettled([
          ...selectedDocs.map((doc) => deleteDocument({ id: doc.id }).unwrap()),
          ...selectedFolders.map((node) => deleteManagerOnce(node.managerFolder!.id)),
        ]);
        managerBulkPending.current = false;
        if (mounted.current) setBulkDeleting(false);
        if (!mounted.current || locationRef.current !== location) return;
        setSelectedKeys(new Set());
        const failures = outcomes.filter((result) => result.status === "rejected").length;
        if (failures)
          showError?.({
            summary: t("validation.error"),
            detail: t("rework.resources.confirm.deleteManagerPartial", { failed: failures, count: outcomes.length }),
          });
        else
          showSuccess?.({
            summary: t(
              selectedDocs.length ? "documentLibrary.removeSuccess" : "rework.resources.toast.deleteFolderSuccess",
            ),
          });
      },
    });
    return;
  };
  // Inclusion applies to every published document, including Parquet-only datasets.
  const searchToggleMode = useMemo<"exclude" | "include" | undefined>(() => {
    const toggleable = selectedDocs;
    if (toggleable.length === 0) return undefined;
    const excludedCount = toggleable.filter((doc) => doc.retrievable === false).length;
    if (excludedCount === 0) return "exclude";
    if (excludedCount === toggleable.length) return "include";
    return undefined;
  }, [selectedDocs]);
  const toggleSearchable = async (doc: ResourceDocument) => {
    try {
      await setDocumentRetrievable(doc, !doc.retrievable);
    } catch {
      showError({ summary: t("validation.error") });
    }
  };
  const bulkToggleSearchable = async () => {
    // The selection is uniform: all included or all excluded, including tables.
    await Promise.all(selectedDocs.map((doc) => toggleSearchable(doc)));
    setSelectedKeys(new Set());
  };
  const [bulkExcluding, setBulkExcluding] = useState(false);
  const bulkExcludeSelection = async () => {
    setBulkExcluding(true);
    try {
      const folderDocs = selectedFolders.length > 0 ? (await resolveFolderDocs(selectedFolders)).map((e) => e.doc) : [];
      // Union of loose selected docs + every document under the selected folders,
      // deduplicated, keeping only those actually excludable and still searchable.
      const byUid = new Map<string, ResourceDocument>();
      for (const doc of [...selectedDocs, ...folderDocs]) byUid.set(doc.id, doc);
      const targets = [...byUid.values()].filter((doc) => doc.retrievable !== false);
      if (targets.length === 0) {
        showInfo?.({ summary: t("rework.resources.toast.bulkExcludeNothing") });
        setSelectedKeys(new Set());
        return;
      }
      const done = await Promise.all(
        targets.map((doc) =>
          setDocumentRetrievable(doc, false)
            .then(() => doc.id)
            .catch(() => null),
        ),
      );
      const okCount = done.filter(Boolean).length;
      if (okCount > 0)
        showSuccess?.({ summary: t("rework.resources.toast.bulkExcludedFromSearch", { count: okCount }) });
      else showError?.({ summary: t("rework.resources.toast.bulkExcludeError") });
      setSelectedKeys(new Set());
    } catch (e: unknown) {
      showError?.({
        summary: t("validation.error"),
        detail:
          (
            e as {
              data?: {
                detail?: string;
              };
            }
          )?.data?.detail ?? t("rework.resources.toast.bulkExcludeError"),
      });
    } finally {
      setBulkExcluding(false);
    }
  };
  const managerFolderPaths = useRef(new Map<string, Promise<string>>());
  const ensureManagerFolderPath = async (segments: string[]): Promise<string | null> => {
    let parent = uploadTargetNode.managerFolder?.id ?? null;
    for (const segment of segments) {
      // The control plane stores folder names in NFC without surrounding whitespace.
      const name = segment.normalize("NFC").trim();
      const key = JSON.stringify([managerSpaceId, parent, name]);
      let pending = managerFolderPaths.current.get(key);
      if (!pending) {
        const parentId = parent;
        pending = (async () => {
          try {
            return (
              await createManagerFolder({
                createFolder: { space_id: managerSpaceId, parent_id: parentId, name },
              }).unwrap()
            ).id;
          } catch (error) {
            if (
              (
                error as {
                  status?: number;
                }
              ).status !== 409
            )
              throw error;
            let offset = 0;
            for (;;) {
              const page = await findManagerEntries({
                id: managerSpaceId,
                parentId: parentId ?? undefined,
                search: name,
                limit: 200,
                offset,
              }).unwrap();
              const match = page.items.find((entry) => entry.kind === "folder" && entry.data.name === name);
              if (match) return match.data.id;
              offset += page.items.length;
              if (!page.items.length || offset >= page.total) throw error;
            }
          }
        })();
        managerFolderPaths.current.set(key, pending);
        void pending.catch(() => managerFolderPaths.current.delete(key));
      }
      parent = await pending;
    }
    return parent;
  };
  const moreOptionsForFolder = (node: FolderNode): OptionModel<"rename" | "delete">[] => {
    if (!canCreateFolder || !node.managerFolder) return [];
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
  const moreOptionsForDoc = (doc: ResourceDocument): OptionModel<DocMenuAction>[] => {
    const activeTask = doc.processing?.status === "pending" || doc.processing?.status === "running";
    const options: OptionModel<DocMenuAction>[] = [];
    options.push({
      value: "download",
      key: "download",
      label: t("rework.resources.action.download"),
      icon: { category: "outlined", type: "download" },
    });
    if (canCreateFolder) {
      const excludedFromSearch = doc.retrievable === false;
      options.push(
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
        ...(isRelaunchable(doc)
          ? [
              {
                value: "relaunch" as const,
                key: "relaunch",
                label: t("rework.resources.action.relaunchIngestion"),
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
          // Deletion must wait until ingestion stops writing.
          disabled: !!activeTask,
          ...(activeTask ? { tooltip: t("rework.resources.action.deleteDisabledWhileProcessing") } : {}),
        },
      );
    }
    return options.filter((option) => option.value !== "relaunch" || directory?.processing_enabled);
  };
  // Two of the tracks after "Auteur" hold nothing most of the time: a settled
  // document shows no chip at all, and the search-exclusion icon is rare. They
  // still reserved their full width on every row, which is what made the table
  // refuse to narrow. Both grids read the same track list, so deciding this
  // once here keeps the header and the rows in step.
  const showsStatus = filteredRows.some((row) => row.kind === "document" && getDocStatus(row.doc) !== "ready");
  const showsExclusion = filteredRows.some(
    (row) => row.kind === "document" && getDocStatus(row.doc) === "ready" && row.doc.retrievable === false,
  );
  // Only present when some row actually has a state to report — a folder of
  // settled documents shows nothing here, and an always-there track would just
  // be 8rem of blank on every row. Fixed rather than "auto" for the same
  // dual-grid reason as the actions column below. Its usual width fits the
  // widest chip (FR "Traitement..."); it shrinks beside a wide import panel.
  const statusColumn: DataTableColumn<Row> = {
    label: "",
    size: "minmax(0, 8rem)",
    cellRenderer: (row) => {
      if (row.kind === "folder") return null;
      return (
        <StatusChip
          status={getDocStatus(row.doc)}
          errors={managerProcessingErrors(row.doc.processing, t)}
          documentUid={row.doc.id}
        />
      );
    },
  };
  const columns: DataTableColumn<Row>[] = [
    {
      label: columnLabel("name"),
      sortable: true,
      size: "minmax(8rem, 2fr)",
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
        return <DocumentNameCell doc={row.doc} />;
      },
    },
    {
      label: columnLabel("size"),
      sortable: true,
      size: "minmax(0, 6.5rem)",
      cellRenderer: (row) => {
        if (row.kind === "folder") {
          return <span className={styles.nowrapCell}>—</span>;
        }
        return <span className={styles.nowrapCell}>{formatBytes(row.doc.size ?? 0)}</span>;
      },
    },
    {
      // Use the time this original was stored in the Control Plane.
      label: columnLabel("created"),
      sortable: true,
      size: "minmax(0, 9rem)",
      cellRenderer: (row) => (
        <span className={styles.nowrapCell}>
          {formatDateTime(row.kind === "folder" ? row.node.managerFolder?.created_at : row.doc.created_at)}
        </span>
      ),
    },
    {
      label: t("rework.resources.columns.author"),
      size: "minmax(0, 9rem)",
      cellRenderer: (row) => {
        const uid = row.kind === "document" ? row.doc.created_by : null;
        if (!uid) return <span className={styles.nowrapCell}>—</span>;
        // The manager listing resolves names itself, in the same response.
        const managerName = directory?.uploaders[uid];
        return <span className={styles.nowrapCell}>{managerName ?? uid}</span>;
      },
    },
    ...(showsStatus ? [statusColumn] : []),
    {
      label: "",
      size: showsExclusion ? "8rem" : "5.75rem",
      cellRenderer: (row) => {
        // retrievable stays false for the entire ingestion window (it only
        // flips true once vectorization completes), not just for a deliberate
        // exclusion — gate on `ready` too, or this icon flags every
        // still-processing document as "excluded from search".
        const status = row.kind === "document" && getDocStatus(row.doc);
        return (
          <span className={styles.actionsCell}>
            {row.kind === "document" && status === "ready" && row.doc.retrievable === false && (
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
                  onClick={() => setPreviewTarget({ documentUid: row.doc.id, fileName: row.doc.name })}
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
                  if (value === "rename") setRenameTarget(row.node);
                  if (value === "delete") void confirmDeleteFolder(row.node);
                } else {
                  if (value === "download") {
                    void downloadManagerDocument(row.doc).catch(() =>
                      showError({ summary: t("rework.resources.toast.downloadError") }),
                    );
                  }
                  if (value === "searchable") void toggleSearchable(row.doc);
                  if (value === "relaunch") void relaunchIngestion([row.doc]);
                  if (value === "delete" && row.doc) {
                    const id = row.doc.id;
                    showConfirmationDialog({
                      title: t("rework.resources.action.delete"),
                      message: t("rework.resources.confirm.deleteManagerDocument", {
                        name: documentDisplayName(row.doc),
                      }),
                      onConfirm: async () => {
                        if (!mounted.current || locationRef.current !== location) return;
                        try {
                          await deleteDocument({ id }).unwrap();
                          if (mounted.current && locationRef.current === location)
                            showSuccess?.({ summary: t("documentLibrary.removeSuccess") });
                        } catch (e) {
                          if (mounted.current && locationRef.current === location)
                            showError?.({
                              summary: t("validation.error"),
                              detail:
                                (
                                  e as {
                                    data?: {
                                      detail?: string;
                                    };
                                  }
                                ).data?.detail ?? t("validation.error"),
                            });
                        }
                      },
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
    return [
      { label: t("rework.resources.roots.resources"), onClick: currentFull ? () => navigateTo(null) : undefined },
      ...(directory?.ancestors ?? []).map((folder, i, ancestors) => ({
        label: folder.name,
        onClick: i < ancestors.length - 1 ? () => navigateTo(folder.id) : undefined,
      })),
    ];
  }, [currentFull, t, navigateTo, managerSpaceId, directory]);
  const failedInitialLoad = failedManagerRead.current;
  const isEmpty = !managerQuery.isFetching && filteredRows.length === 0;
  const emptyMessage = failedInitialLoad
    ? t("rework.resources.empty.loadError")
    : !currentFull
      ? t("rework.resources.empty.createLibrary")
      : t("rework.resources.empty.folder");
  // The upload drawer targets whichever folder triggered it: a drop target
  // (dropTargetNode) when opened by dragging files onto a folder row, or the
  // currently-viewed folder for the toolbar's "+"/manual upload.
  const uploadTargetNode = dropTargetNode ?? currentNode;
  const atRoot = currentFull === null;
  const pageDroppable = canCreateFolder;
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
      <Dialog
        open={profilePromptOpen}
        title={t("rework.resources.action.relaunchIngestion")}
        confirmLabel={t("rework.resources.action.relaunchIngestion")}
        confirmDisabled={!relaunchProfile}
        onConfirm={() => answerProfile(relaunchProfile)}
        onCancel={() => answerProfile(undefined)}
      >
        <p>{t("rework.resources.relaunchProfileHelp")}</p>
        <Select<Profile>
          size="medium"
          label={t("rework.resources.relaunchProfileLabel")}
          value={relaunchProfile}
          onChange={setRelaunchProfile}
          options={(["fast", "medium", "rich"] as const).map((value) => ({
            key: value,
            value,
            label: t(`documentLibrary.profile${value[0].toUpperCase()}${value.slice(1)}`),
          }))}
        />
      </Dialog>
      {failedInitialLoad && childFolders.length > 0 && (
        <div className={styles.loadError} role="alert">
          {t("rework.resources.empty.loadError")}
        </div>
      )}
      <ResourceExplorer<Row>
        breadcrumb={{
          segments: breadcrumbSegments,
          onBack: navigateBack,
          canGoBack: !atRoot,
          backLabel: t("rework.resources.action.back"),
        }}
        search={{
          value: search,
          onChange: (value) => {
            setSearch(value);
            setFolderOffset(0);
            setSelectedKeys(new Set());
          },
          placeholder: t("rework.resources.search.placeholder"),
          ariaLabel: t("rework.resources.search.ariaLabel"),
          clearAriaLabel: t("rework.resources.search.clearAriaLabel"),
        }}
        toolbarActions={
          hasSelection ? (
            <BulkActionsBar
              selectedCount={selectedDocs.length + selectedFolders.length}
              disabledReason={{
                processing: directory?.processing_enabled ? undefined : t("rework.documentStorage.noProcessing"),
              }}
              onDelete={canCreateFolder ? bulkDelete : undefined}
              deleteLoading={bulkDeleting}
              relaunch={
                canCreateFolder && directory?.processing_enabled && relaunchableSelection.length > 0
                  ? {
                      count: relaunchableSelection.length,
                      onClick: () => void bulkRelaunch(),
                      loading: bulkRelaunching,
                    }
                  : undefined
              }
              onClearSelection={() => setSelectedKeys(new Set())}
              searchToggle={
                !canCreateFolder || !directory?.processing_enabled
                  ? undefined
                  : selectedFolders.length > 0
                    ? { mode: "exclude", onClick: () => void bulkExcludeSelection(), loading: bulkExcluding }
                    : searchToggleMode
                      ? { mode: searchToggleMode, onClick: bulkToggleSearchable }
                      : undefined
              }
            />
          ) : (
            <>
              {/* Outside the write gate on purpose: refreshing the view is not
              a mutation, and a read-only member needs it as much as anyone. */}
              <Tooltip text={t("rework.resources.action.refresh")}>
                <IconButton
                  variant="icon"
                  size="medium"
                  icon={{ category: "outlined", type: "refresh" }}
                  aria-label={t("rework.resources.action.refresh")}
                  loading={refreshing}
                  onClick={() => void refreshView()}
                />
              </Tooltip>
              {canCreateFolder && (
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
                    text={currentFull ? t("rework.resources.action.addFile") : t("rework.resources.action.addFileHint")}
                  >
                    <IconButton
                      color="primary"
                      variant="icon"
                      size="medium"
                      icon={{ category: "outlined", type: "upload_file" }}
                      aria-label={t("rework.resources.action.addFile")}
                      disabled={!currentFull || !directory}
                      onClick={() => setUploadOpen(true)}
                    />
                  </Tooltip>
                </>
              )}
            </>
          )
        }
        loading={managerQuery.isFetching && !directory}
        loadingMessage={t("rework.resources.loading")}
        empty={isEmpty}
        emptyMessage={emptyMessage}
        columns={columns}
        rows={filteredRows}
        rowKey={rowKey}
        selectedKeys={selectedKeys}
        onSelectedKeysChange={setSelectedKeys}
        serverPagination={
          directory
            ? {
                totalCount: directory?.total ?? 0,
                offset: folderOffset,
                limit: rowsPerPage,
                onOffsetChange: (offset) => {
                  setFolderOffset(offset);
                  setSelectedKeys(new Set());
                },
                onLimitChange: handleRowsPerPageChange,
              }
            : undefined
        }
        sortState={sortStateFromOrdering(ordering, columnLabel)}
        onSortChange={handleSortChange}
        sortClearable={false}
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

      <DocumentPreviewDrawer target={previewTarget} onClose={() => setPreviewTarget(null)} />
      <DocumentUploadDrawer
        isOpen={uploadOpen}
        onClose={() => {
          setUploadOpen(false);
          setDroppedFiles(undefined);
          setDropTargetNode(null);
          managerFolderPaths.current.clear();
        }}
        initialFiles={droppedFiles}
        teamId={teamId}
        importScopeId={importScopeId}
        destinationPath={(dropTargetNode?.managerFolder?.path ?? displayPath) || undefined}
        managerDestination={{
          spaceId: managerSpaceId,
          folderId: uploadTargetNode.managerFolder?.id,
          processingEnabled: directory?.processing_enabled,
        }}
        ensureFolderPath={canCreateFolder ? ensureManagerFolderPath : undefined}
        requireFolderPerFile={!uploadTargetNode.managerFolder}
        // Reached long after the drawer closed — the transfer is detached, and
        // by then this workspace may be gone. Refetching a query whose
        // subscription has ended throws, so nothing is refreshed once it is:
        // the next mount fetches anyway.
        onUploadComplete={() => {
          if (!mounted.current) return;
          void managerQuery.refetch();
          onDocumentsChanged?.();
          return;
        }}
      />
      <CreateFolderModal
        key={location}
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        parentPath={displayPath ?? undefined}
        maxDepth={15}
        onSubmit={async (name) => {
          if (!canCreateFolder) throw new Error("forbidden");
          await createManagerFolder({
            createFolder: { space_id: managerSpaceId, parent_id: currentFull, name },
          }).unwrap();
        }}
        onCreated={() => void managerQuery.refetch()}
      />
      {renameTarget && (
        <RenameModal
          key={location}
          open={!!renameTarget}
          onClose={() => setRenameTarget(null)}
          initialName={renameTarget.name}
          onSubmit={async (newName) => {
            if (renameTarget.managerFolder) {
              try {
                await renameManagerFolder({
                  id: renameTarget.managerFolder.id,
                  rename: { name: newName },
                }).unwrap();
              } catch (e) {
                if (mounted.current && locationRef.current === location)
                  showError?.({
                    summary: t("validation.error"),
                    detail:
                      (
                        e as {
                          data?: {
                            detail?: string;
                          };
                        }
                      ).data?.detail ?? t("rework.resources.folderModal.error"),
                  });
                throw e;
              }
            }
          }}
        />
      )}
    </div>
  );
}
export default DocumentWorkspace;
