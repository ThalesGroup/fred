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
import {
  type DocumentMetadata,
  type OwnerFilter,
  type TagWithItemsId,
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation,
  useCreateTagMutation,
  useDeleteTagMutation,
  useListTagsQuery,
  useListTasksKnowledgeFlowV1TasksGetQuery,
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation,
  useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation,
  useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import {
  buildTree,
  collectDescendantTagIds,
  findNode,
  fullPath,
  withoutMachineWritten,
  type TagNode,
} from "../../../../../shared/utils/tagTree.ts";
import { selectAllTasks, selectActiveTasks } from "../../../../features/tasks/taskSlice";
import { TERMINAL_STATES, type TaskViewModel } from "../../../../features/tasks/taskTypes";
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
import CreateFolderModal from "../CreateFolderModal/CreateFolderModal.tsx";
import ManageLabelsModal from "../ManageLabelsModal/ManageLabelsModal.tsx";
import RenameModal from "../RenameModal/RenameModal.tsx";
import { StatusChip } from "@shared/molecules/StatusChip/StatusChip.tsx";
import type { DocStatus } from "@shared/atoms/DocStatusBadge/DocStatusBadge.tsx";
import BulkActionsBar from "../BulkActionsBar/BulkActionsBar.tsx";
import { deriveDocStatus, isTabularOnlyDoc } from "@shared/molecules/StatusChip/deriveDocStatus.ts";
import { pagesToRefreshOnTaskCompletion } from "./refreshOnCompletion.ts";
import {
  buildFolderRollups,
  collectFailedDocsByTag,
  indexFoldersByDocUid,
  resolveDocOutcomes,
} from "./folderRollups.ts";
import styles from "./DocumentWorkspace.module.css";
import {
  DEFAULT_ORDERING,
  SORTABLE_COLUMN_KEYS,
  orderingFromSortState,
  sortStateFromOrdering,
  type DocumentOrdering,
  type DocumentSortField,
} from "./documentOrdering.ts";

const DEFAULT_PAGE_SIZE = 50;
// Port of main's DocumentLibraryList live-status loop: while a loaded row is
// processing, its folder page is reloaded on this cadence so the badge flips
// to Ready/Failed without a manual refresh.
const DOC_STATUS_POLL_MS = 3000;
// Separator for the memo keys the folder rollup below tracks its live inputs
// by. NUL can never appear inside a tag id or a document uid, so two different
// id sets can never join to the same string — unlike a comma, which a
// scheduler-pull uid (`pull-{source_tag}-{hash}`, from a configurable tag)
// could carry. Keys are compared, never split back apart.
const KEY_SEP = "\u0000";
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
  /** The library this workspace is rooted at, by tag id — the breadcrumb
   * starts there and nothing above it is reachable. Given as an id rather than
   * a path because that is what a caller holds and because a path can be
   * renamed underneath it. Absent means the team corpus itself, which is also
   * the only mode that leaves out the libraries a machine fills: once inside
   * one, its contents are precisely what you came to see. */
  rootTagId?: string;
  /** Offer no way to write. A Knowledge Base library is filled by its pod and
   * the backend refuses every person-facing mutation against it, so upload,
   * folder creation, rename, move, deletion and the bulk selection they serve
   * are absent rather than shown disabled. Reading — opening, previewing,
   * downloading, searching — is untouched. */
  readOnly?: boolean;
}

/** The "User Assets" tag is surfaced in its own tab, not in the folder tree. */
const isUserAssetsTag = (name: string, path?: string | null) => name === "User Assets" || path === "user-assets";

type Row = { kind: "folder"; node: TagNode } | { kind: "document"; doc: DocumentMetadata };

type DocMenuAction = "rename" | "download" | "searchable" | "relaunch" | "delete" | "labels";

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

function rowLabel(row: Row): string {
  return row.kind === "folder" ? row.node.name : documentDisplayName(row.doc);
}

// Every tag under `node` (its sub-folders included) paired with the directory it
// sits at, expressed relative to `basePrefix` (the folder currently being
// viewed). Used by the bulk download to mirror the on-disk tree inside the ZIP —
// a selected folder "Reports" viewed from "A/B" yields `relDir` values like
// "Reports" and "Reports/2024", so its documents zip under those paths.
// collectDescendantTagIds returns ids only; this keeps the path alongside each.
function descendantTagsWithPaths(node: TagNode, basePrefix: string): { tagId: string; relDir: string }[] {
  const out: { tagId: string; relDir: string }[] = [];
  const prefix = basePrefix ? `${basePrefix}/` : "";
  const walk = (n: TagNode) => {
    const relDir = prefix && n.full.startsWith(prefix) ? n.full.slice(prefix.length) : n.full;
    n.tagsHere.forEach((tag) => out.push({ tagId: tag.id, relDir }));
    n.children.forEach((child) => walk(child));
  };
  walk(node);
  return out;
}

/**
 * Corpus d'équipe tab (RFC §13, Resources dashboard v2): breadcrumb drill-down
 * through one library (tag) level at a time — replaces the pre-FRONT-09.G
 * always-expanded tree — with a `DataTable` of the current folder's direct
 * children (subfolders + documents). Heavy listing stays on the backend:
 * folders lazy-load their first document page on entry.
 */
function DocumentWorkspace({
  teamId,
  isPersonalTeam,
  onDocumentsChanged,
  rootTagId,
  readOnly = false,
}: DocumentWorkspaceProps) {
  const { t } = useTranslation();
  // One place the sortable columns get their label, shared by the column
  // definitions and by the sort-state translation both ways.
  const columnLabel = useCallback((field: DocumentSortField) => t(SORTABLE_COLUMN_KEYS[field]), [t]);
  const { showSuccess, showError, showWarn, showInfo } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();
  const activeTasks = useSelector(selectActiveTasks);

  const { data: team } = useGetTeamQuery({ teamId });
  const { canUpdateResources } = useTeamCapabilities(team);
  // The single gate every write affordance already passes through — folder and
  // document menus, both drop targets, the toolbar, folder creation on upload.
  // A read-only workspace withholds them exactly as a member lacking the
  // capability does, which is right: the backend refuses a person's write into
  // a machine-filled library, so offering the action could only produce a
  // failed request. Reading is untouched — download is deliberately outside
  // this gate below.
  const canCreateFolder = canUpdateResources && !readOnly;

  const ownerFilter: OwnerFilter = isPersonalTeam ? "personal" : "team";
  const {
    data: tags,
    isLoading: tagsLoading,
    refetch: refetchTagsQuery,
  } = useListTagsQuery({
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

  // Has the library we were rooted at been found? Not yet loaded and deleted
  // look the same here, and both must withhold: `baseFull` below would be null
  // either way, which is also the corpus-root sentinel, and a rooted tree
  // carries every team tag. Without this the page would answer "show me one
  // library" with the whole corpus — and a library outliving its folder is a
  // supported state, since deleting one stays available to people.
  const rootResolved = !rootTagId || (tags ?? []).some((tag) => tag.id === rootTagId);

  const tree = useMemo(() => {
    const documentTags = (tags ?? []).filter((tag) => !isUserAssetsTag(tag.name, tag.path));
    // Rooted inside one library, everything it holds is in scope — the filter
    // only applies to the corpus, where a machine-filled library is not one of
    // the folders people manage.
    if (!rootResolved) return buildTree([]);
    return buildTree(rootTagId ? documentTags : withoutMachineWritten(documentTags));
  }, [tags, rootTagId, rootResolved]);

  // Where the breadcrumb starts: null at the Corpus root (the tree's synthetic
  // top node), or the path of the library this workspace was rooted at.
  const baseFull = useMemo(() => {
    if (!rootTagId) return null;
    const rootTag = (tags ?? []).find((tag) => tag.id === rootTagId);
    return rootTag ? fullPath(rootTag) : null;
  }, [tags, rootTagId]);

  const [currentFolderFull, setCurrentFolderFull] = useState<string | null>(null);
  // Null means the base, wherever that is — so navigation keeps working across
  // the render where `baseFull` resolves.
  const currentFull = currentFolderFull ?? baseFull;
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
  // The SSE task feed updates badges before processing stages reach the browse snapshot.
  const activeDocTaskByUid = useMemo(() => {
    const byUid = new Map<string, TaskViewModel>();
    for (const task of activeTasks) {
      if (task.target?.type === "document" && task.target.id) byUid.set(task.target.id, task);
    }
    return byUid;
  }, [activeTasks]);
  // Team history includes terminal outcomes; personal history needs explicit state queries.
  const { data: taskHistory } = useListTasksKnowledgeFlowV1TasksGetQuery(
    isPersonalTeam ? { scope: "user", kind: "ingestion" } : { scope: "team", teamId, kind: "ingestion" },
  );
  // User-scoped listing hides terminal tasks unless a state is explicitly requested.
  const { data: personalFailures } = useListTasksKnowledgeFlowV1TasksGetQuery(
    { scope: "user", kind: "ingestion", state: "failed" },
    { skip: !isPersonalTeam },
  );
  const { data: personalSuccesses } = useListTasksKnowledgeFlowV1TasksGetQuery(
    { scope: "user", kind: "ingestion", state: "succeeded" },
    { skip: !isPersonalTeam },
  );
  const allTasks = useSelector(selectAllTasks);
  // Keyed on the session's terminal outcomes, not on `allTasks` itself: the task
  // store is a fresh array on EVERY SSE progress event, and re-ranking the
  // team's whole history on each one is precisely what the poll interval's
  // `pendingTagKey` goes to such lengths to avoid.
  const liveOutcomeKey = allTasks
    .filter((task) => TERMINAL_STATES.has(task.state) && task.target?.type === "document")
    .map((task) => `${task.target?.id}:${task.state}`)
    .sort()
    .join(KEY_SEP);
  const docOutcomes = useMemo(
    () =>
      resolveDocOutcomes(
        [...(taskHistory?.tasks ?? []), ...(personalFailures?.tasks ?? []), ...(personalSuccesses?.tasks ?? [])],
        allTasks,
      ),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see liveOutcomeKey
    [taskHistory, personalFailures, personalSuccesses, liveOutcomeKey],
  );

  // Documents that finished during THIS browser session. Read from the Redux
  // store ALONE, deliberately — the history exists only to rank outcomes, and
  // folding it in here would mark every document the team ever ingested as
  // "just finished", turning a transient "your upload landed" cue into a
  // permanent green tick on every ready row (#2315).
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
      : !activeDocTaskByUid.has(doc.identity.document_uid) && docOutcomes.failed.has(doc.identity.document_uid)
        ? "failed"
        : deriveDocStatus(doc, activeDocTaskByUid.get(doc.identity.document_uid)).status;
  // A TEAMMATE's ingestion is invisible in `activeTasks`: the SSE store is
  // user-scoped (useTaskRehydration fetches scope=user), so only one's own
  // tasks land there. The team listing above carries everyone's, in-flight
  // ones included — `scope=team` does not exclude terminal states, so it is
  // the only place a colleague's running ingestion shows up.
  const liveTeamDocUids = useMemo(() => {
    const uids = new Set<string>();
    for (const task of taskHistory?.tasks ?? []) {
      if (!TERMINAL_STATES.has(task.state) && task.target?.type === "document" && task.target.id) {
        uids.add(task.target.id);
      }
    }
    return uids;
  }, [taskHistory]);
  // Relaunching exists to unblock, not to re-run a pipeline on demand: offered
  // on an ingestion that failed, never ran, or claims to be running while no
  // task actually is (dead worker, dropped workflow). Anything still running —
  // one's own, a teammate's, or a relaunch just clicked — means a second call
  // would only duplicate it.
  const isRelaunchable = (doc: DocumentMetadata): boolean => {
    const uid = doc.identity.document_uid;
    if (reprocessOverrides[uid] || activeDocTaskByUid.has(uid) || liveTeamDocUids.has(uid)) return false;
    const status = getDocStatus(doc);
    return status === "failed" || status === "raw" || status === "processing";
  };
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
  // Ordering travels to the server with every browse: only one page comes
  // back, so sorting it in the browser would order 50 rows and call it a
  // sorted folder. Same lifetime as rowsPerPage — one setting for the view.
  const [ordering, setOrdering] = useState<DocumentOrdering>(DEFAULT_ORDERING);

  const [browseDocumentsByTag] = useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();
  const [fetchTagSizes] = useTagSizesKnowledgeFlowV1DocumentsMetadataTagSizesPostMutation();
  const [processDocuments] = useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation();
  const [deleteTag] = useDeleteTagMutation();
  const [createTag] = useCreateTagMutation();
  // Direct retrievable mutation for the folder-aware "exclude from search" bulk
  // action (#2446): a folder's descendant documents are toggled one PUT each,
  // and unlike commands.toggleRetrievable this stays silent so a large subtree
  // shows a single summary toast instead of one per document.
  const [updateRetrievable] =
    useUpdateDocumentMetadataRetrievableKnowledgeFlowV1DocumentMetadataDocumentUidPutMutation();

  const currentNode = currentFull ? findNode(tree, currentFull) : tree;
  const currentTag = currentNode.tagsHere[0] ?? null;

  const loadTagPage = useCallback(
    async (tagId: string, offset: number, limit: number = rowsPerPage, sort: DocumentOrdering = ordering) => {
      setPerTag((prev) => ({
        ...prev,
        [tagId]: { docs: prev[tagId]?.docs ?? [], total: prev[tagId]?.total ?? 0, offset, loading: true },
      }));
      try {
        const res = await browseDocumentsByTag({
          browseDocumentsByTagRequest: { tag_id: tagId, offset, limit, sort_by: sort.by, sort_order: sort.order },
        }).unwrap();
        setPerTag((prev) => ({
          ...prev,
          [tagId]: { docs: res.documents ?? [], total: res.total ?? 0, offset, loading: false },
        }));
      } catch {
        setPerTag((prev) => ({ ...prev, [tagId]: { ...prev[tagId], loading: false } as PageState }));
      }
    },
    [browseDocumentsByTag, rowsPerPage, ordering],
  );

  const handleRowsPerPageChange = useCallback(
    (limit: number) => {
      setRowsPerPage(limit);
      if (currentTag) void loadTagPage(currentTag.id, 0, limit);
    },
    [currentTag, loadTagPage],
  );

  // Back to the first page: page 3 of a name-ordered folder holds different
  // documents than page 3 of a size-ordered one, so keeping the offset would
  // land the reader in an unrelated slice. The new ordering is passed
  // explicitly for the same reason `handleRowsPerPageChange` passes its limit
  // — `loadTagPage` would otherwise close over the pre-update state.
  const handleSortChange = useCallback(
    (next: SortState | null) => {
      const sort = orderingFromSortState(next, columnLabel);
      setOrdering(sort);
      if (currentTag) void loadTagPage(currentTag.id, 0, rowsPerPage, sort);
    },
    [currentTag, loadTagPage, rowsPerPage, columnLabel],
  );

  // Explicit "reload what I'm looking at". The knowledge-flow cache now serves
  // the previous answer for a short window instead of refetching on every
  // mount, which is what makes coming back to this page instant — this is the
  // way to force the round trip when you know someone else has just changed
  // something. refetchTags also refreshes the usage stats and the storage
  // quota, so one press updates the whole view.
  const [refreshing, setRefreshing] = useState(false);
  const refreshView = useCallback(async () => {
    setRefreshing(true);
    try {
      const tagId = currentTag?.id;
      await Promise.all([
        refetchTags(),
        tagId ? loadTagPage(tagId, perTagRef.current[tagId]?.offset ?? 0) : Promise.resolve(),
      ]);
    } finally {
      setRefreshing(false);
    }
  }, [refetchTags, loadTagPage, currentTag]);

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
  // Refresh document state and quota after a durable terminal task event.
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

  // `POST /process-documents` takes a `files` array, so a multi-selection costs
  // the same single round trip as one row. Returns whether the call went
  // through — the caller clears its selection only then.
  const relaunchIngestion = useCallback(
    async (docs: DocumentMetadata[], tagId: string): Promise<boolean> => {
      if (docs.length === 0) return false;
      try {
        await processDocuments({
          processDocumentsRequest: {
            files: docs.map((doc) => ({
              source_tag: doc.source?.source_tag ?? "",
              document_uid: doc.identity.document_uid,
              profile: "fast",
              tags: doc.tags?.tag_ids ?? [tagId],
            })),
            pipeline_name: "profile-fast",
          },
        }).unwrap();
        showSuccess?.({ summary: t("rework.resources.toast.relaunchStarted", { count: docs.length }) });
        const deadline = Date.now() + REPROCESS_OVERRIDE_TTL_MS;
        setReprocessOverrides((prev) => ({
          ...prev,
          ...Object.fromEntries(
            docs.map((doc) => [
              doc.identity.document_uid,
              { snapshot: JSON.stringify(doc.processing?.stages ?? {}), deadline },
            ]),
          ),
        }));
        await loadTagPage(tagId, perTag[tagId]?.offset ?? 0);
        return true;
      } catch (e: unknown) {
        showError?.({
          summary: t("validation.error"),
          detail: (e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.toast.relaunchError"),
        });
        return false;
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
              if (currentFull === node.full)
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
      currentFull,
      navigateTo,
    ],
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
  // Folders always come first (they are prepended to the rows below, never
  // interleaved); this orders them among themselves by the same key the
  // server applies to the documents. They come from the in-memory tag tree,
  // not from the paginated browse, so their order is ours to compute.
  const childFolders = useMemo(() => {
    const nodes = [...currentNode.children.values()];
    const direction = ordering.order === "desc" ? -1 : 1;
    if (ordering.by === "created") {
      const at = (node: TagNode) => Date.parse(node.tagsHere[0]?.created_at ?? "") || 0;
      return nodes.sort((a, b) => direction * (at(a) - at(b)));
    }
    // A folder has no size of its own — its rollup is fetched per view and is
    // not known here — so ordering by size falls back to the name, which at
    // least keeps the group stable instead of shuffling it.
    return nodes.sort((a, b) => direction * a.name.localeCompare(b.name));
  }, [currentNode, ordering]);

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

  // #2384 — a folder row summarizes the ingestion state of everything under it
  // (its own documents + every sub-folder's, at any depth): still processing,
  // some failed, or all finished during this session. Without it, the only way
  // to tell whether a bulk upload has landed is to walk into each sub-folder
  // and read the rows one by one.
  //
  // Every input is already in memory — no new endpoint, no new backend status.
  // Two families of source, unioned per state because neither subsumes the
  // other:
  //  - the ALREADY-LOADED pages (`perTag`), read per tag id. Survives a page
  //    reload, and is the only source that sees what the browse snapshot knows
  //    and the task feed cannot: a teammate's ingestion, or a document a dead
  //    worker left `in_progress`/failed (#2279). Limited to folders visited
  //    this session — but without it a folder could read "settled" while a row
  //    inside it visibly spins, the exact confusion this feature removes.
  //  - the SSE task feed, matched against the tag tree's `item_ids`. Reaches
  //    folders that were never opened, but carries only the current user's
  //    tasks (`GET /tasks?scope=user`, useTaskRehydration) and — since that
  //    route hides terminal tasks — only for this browser session.
  //
  // Hence the deliberate asymmetry between the two rolled-up terminal states:
  // "all done" is session-only (it is a transient "your upload landed", and
  // the memory-only task store expires it for free on refresh), while a
  // failure stays visible for every folder the snapshot covers, because it
  // still needs someone to act on it.
  const failedDocsByTagId = useMemo(() => collectFailedDocsByTag(perTag, documentDisplayName), [perTag]);
  const folderByDocUid = useMemo(() => indexFoldersByDocUid(childFolders), [childFolders]);

  // Stable keys for the live inputs: the task store is a fresh object on EVERY
  // SSE progress event, so depending on those identities would recompute on each
  // one — the same trap `pendingTagKey` avoids for the poll interval above.
  // Joined on NUL rather than a comma because a document uid is not always a
  // plain uuid (scheduler pulls build `pull-{source_tag}-{hash}` from a
  // configurable tag), and two different sets must not collide onto the same
  // key. These are memo keys only — never split back apart. The failure key
  // carries the NAMES too: `taskEventReceived` rewrites `target` on any event
  // that carries one, so a label refined after the failure was first recorded
  // must still reach the tooltip.
  const pendingTagIdsKey = [...pendingTagIds].sort().join(KEY_SEP);
  const activeDocUidKey = [...activeDocTaskByUid.keys()].sort().join(KEY_SEP);
  const failedDocKey = [...docOutcomes.failed]
    .map(([uid, doc]) => `${uid}${KEY_SEP}${doc.name}${KEY_SEP}${doc.error ?? ""}`)
    .sort()
    .join(KEY_SEP);
  const justCompletedKey = [...justCompletedDocUids].sort().join(KEY_SEP);

  const folderRollups = useMemo(
    () =>
      buildFolderRollups({
        childFolders,
        tagIdsByFolder: folderDescendantTagIds,
        folderByDocUid,
        pendingTagIds,
        failedDocsByTagId,
        activeDocUids: activeDocTaskByUid.keys(),
        outcomes: docOutcomes,
        justCompletedDocUids,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps -- see the key block
    // above: the live inputs are read from their sources, tracked by key.
    [
      childFolders,
      folderDescendantTagIds,
      folderByDocUid,
      failedDocsByTagId,
      docOutcomes,
      pendingTagIdsKey,
      activeDocUidKey,
      failedDocKey,
      justCompletedKey,
    ],
  );

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

  // Selected folder rows (#2446). Folder checkboxes have always rendered but did
  // nothing; these now drive the same contextual bar as documents, with every
  // action applied recursively to the folder's contents.
  const selectedFolders = useMemo(
    () =>
      filteredRows
        .filter((row): row is Row & { kind: "folder" } => row.kind === "folder" && selectedKeys.has(rowKey(row)))
        .map((row) => row.node),
    [filteredRows, selectedKeys],
  );

  // Page through every document under one tag. A folder bulk action can span a
  // large subtree, so this is deliberately called only when the action fires
  // (never on selection) — ticking a folder box must stay instant.
  const fetchAllDocsForTag = useCallback(
    async (tagId: string): Promise<DocumentMetadata[]> => {
      const PAGE = 200;
      const first = await browseDocumentsByTag({
        browseDocumentsByTagRequest: { tag_id: tagId, offset: 0, limit: PAGE },
      }).unwrap();
      const docs = [...(first.documents ?? [])];
      const total = first.total ?? docs.length;
      for (let offset = PAGE; offset < total; offset += PAGE) {
        const next = await browseDocumentsByTag({
          browseDocumentsByTagRequest: { tag_id: tagId, offset, limit: PAGE },
        }).unwrap();
        docs.push(...(next.documents ?? []));
      }
      return docs;
    },
    [browseDocumentsByTag],
  );

  // Resolve every document under the given folders, each paired with the ZIP-
  // relative directory it lives in (for `bulkDownload`'s structure). Fetched on
  // demand, deduplicated by uid (a document is tagged into exactly one folder,
  // but the walk does not rely on it).
  const resolveFolderDocs = useCallback(
    async (folders: TagNode[]): Promise<{ doc: DocumentMetadata; relDir: string }[]> => {
      const tagEntries = folders.flatMap((node) => descendantTagsWithPaths(node, currentNode.full));
      const perTagResults = await Promise.all(
        tagEntries.map(async ({ tagId, relDir }) => (await fetchAllDocsForTag(tagId)).map((doc) => ({ doc, relDir }))),
      );
      const seen = new Set<string>();
      const out: { doc: DocumentMetadata; relDir: string }[] = [];
      for (const entry of perTagResults.flat()) {
        if (seen.has(entry.doc.identity.document_uid)) continue;
        seen.add(entry.doc.identity.document_uid);
        out.push(entry);
      }
      return out;
    },
    [fetchAllDocsForTag, currentNode.full],
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
    if (!currentTag || relaunchableSelection.length === 0) return;
    setBulkRelaunching(true);
    try {
      if (await relaunchIngestion(relaunchableSelection, currentTag.id)) setSelectedKeys(new Set());
    } finally {
      setBulkRelaunching(false);
    }
  };

  // Delete is folder-aware (#2446): each selected folder's tag is deleted (the
  // backend cascades to sub-folders + their documents, same path as the single-
  // folder delete), and the loose selected documents are untagged from the
  // current folder. A precise recursive count is deliberately NOT recomputed
  // here — that would cost one browse per subtree tag; the confirmation warns
  // generically once folders are involved, while the single-folder delete keeps
  // its live count.
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const bulkDelete = () => {
    if (!hasSelection) return;
    const docCount = selectedDocs.length;
    const folderCount = selectedFolders.length;
    const message =
      folderCount === 0
        ? t("rework.resources.confirm.deleteBulkMessage", { count: docCount })
        : docCount === 0
          ? t("rework.resources.confirm.deleteFoldersMessage", { count: folderCount })
          : t("rework.resources.confirm.deleteMixedMessage", { folderCount, docCount });
    showConfirmationDialog({
      title: t("rework.resources.confirm.deleteTitle"),
      message,
      onConfirm: async () => {
        setBulkDeleting(true);
        try {
          await Promise.all(
            selectedFolders.map((node) => {
              const tag = node.tagsHere[0];
              return tag ? deleteTag({ tagId: tag.id }).unwrap() : Promise.resolve();
            }),
          );
          if (docCount > 0 && currentTag) {
            // Handles its own success toast + tag/doc refresh.
            await commands.bulkRemoveFromLibraryForTag(selectedDocs, currentTag as unknown as TagWithItemsId);
          }
          if (folderCount > 0) {
            showSuccess?.({ summary: t("rework.resources.toast.deleteFolderSuccess") });
            void refetchTags();
          }
          setSelectedKeys(new Set());
        } catch (e: unknown) {
          showError?.({
            summary: t("validation.error"),
            detail:
              (e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.toast.deleteFolderError"),
          });
        } finally {
          setBulkDeleting(false);
        }
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

  // Folder-aware "exclude from search" (#2446). When the selection contains a
  // folder there is no cheap way to know the uniform retrievable state of its
  // subtree, so this is not the directional file-only toggle: it resolves every
  // descendant document on click (spinner meanwhile) and forces `retrievable`
  // to false on all of them — the one direction the user asked for at the folder
  // level. Silent per-document mutation with a single summary toast, unlike
  // bulkToggleSearchable's one-toast-per-doc path (kept for the file-only case).
  const [bulkExcluding, setBulkExcluding] = useState(false);
  const bulkExcludeSelection = async () => {
    setBulkExcluding(true);
    try {
      const folderDocs = selectedFolders.length > 0 ? (await resolveFolderDocs(selectedFolders)).map((e) => e.doc) : [];
      // Union of loose selected docs + every document under the selected folders,
      // deduplicated, keeping only those actually excludable and still searchable.
      const byUid = new Map<string, DocumentMetadata>();
      for (const doc of [...selectedDocs, ...folderDocs]) byUid.set(doc.identity.document_uid, doc);
      const targets = [...byUid.values()].filter((doc) => !isTabularOnlyDoc(doc) && doc.source.retrievable !== false);
      if (targets.length === 0) {
        showInfo?.({ summary: t("rework.resources.toast.bulkExcludeNothing") });
        setSelectedKeys(new Set());
        return;
      }
      const done = await Promise.all(
        targets.map((doc) =>
          updateRetrievable({ documentUid: doc.identity.document_uid, retrievable: false })
            .unwrap()
            .then(() => doc.identity.document_uid)
            .catch(() => null),
        ),
      );
      // Patch any loaded page holding a just-excluded document (folder docs are
      // off-screen, so this only touches the loose-doc rows — the rest are not
      // rendered anyway).
      for (const uid of done) if (uid) patchDocRetrievable(uid, false);
      const okCount = done.filter(Boolean).length;
      if (okCount > 0)
        showSuccess?.({ summary: t("rework.resources.toast.bulkExcludedFromSearch", { count: okCount }) });
      else showError?.({ summary: t("rework.resources.toast.bulkExcludeError") });
      setSelectedKeys(new Set());
    } catch (e: unknown) {
      showError?.({
        summary: t("validation.error"),
        detail: (e as { data?: { detail?: string } })?.data?.detail ?? t("rework.resources.toast.bulkExcludeError"),
      });
    } finally {
      setBulkExcluding(false);
    }
  };

  // Non-destructive and repeatable — unlike delete/exclude above, the
  // selection is left as-is afterward (a user may well want to act on the
  // same rows again right after downloading them).
  const [bulkDownloading, setBulkDownloading] = useState(false);
  const bulkDownload = async () => {
    setBulkDownloading(true);
    try {
      // Folder-aware (#2446): resolve each selected folder's documents and zip
      // them under their folder-relative path, preserving the tree; loose
      // selected documents sit at the archive root. Resolved on click so a
      // folder selection stays instant until the user actually downloads.
      const folderDocs = selectedFolders.length > 0 ? await resolveFolderDocs(selectedFolders) : [];
      const files = [
        ...selectedDocs.map((doc) => ({
          filename: doc.identity.document_name || doc.identity.document_uid,
          fetchBlob: () => commands.fetchBlob(doc),
        })),
        ...folderDocs.map(({ doc, relDir }) => {
          const name = doc.identity.document_name || doc.identity.document_uid;
          return { filename: relDir ? `${relDir}/${name}` : name, fetchBlob: () => commands.fetchBlob(doc) };
        }),
      ];
      if (files.length === 0) {
        // Folders-only selection that resolved to no documents — give feedback
        // rather than a silently dead click after the spinner.
        showInfo?.({ summary: t("rework.resources.toast.downloadEmpty") });
        return;
      }
      await downloadManyAsZip(files, "resources.zip");
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
    return options;
  };

  const columns: DataTableColumn<Row>[] = [
    {
      label: columnLabel("name"),
      sortable: true,
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
        return <DocumentNameCell doc={row.doc} />;
      },
    },
    {
      label: columnLabel("size"),
      sortable: true,
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
      label: columnLabel("created"),
      sortable: true,
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
        // Folder rollup (#2384). Precedence is processing > failures > done:
        // while anything is still running the folder is not settled yet, and
        // once it is, an unresolved failure is more actionable than a "your
        // upload landed" marker. `raw` is never rolled up — a folder holding
        // never-processed documents is a normal steady state, not news.
        if (row.kind === "folder") {
          const rollup = folderRollups.get(row.node.full);
          if (rollup?.processing) return <StatusChip status="processing" />;
          if (rollup?.failed.length) return <StatusChip status="warning" failedDocuments={rollup.failed} />;
          return rollup?.justDone ? <StatusChip status="ready" justCompleted /> : null;
        }
        return (
          <StatusChip
            status={getDocStatus(row.doc)}
            errors={row.doc.processing?.errors}
            documentUid={row.doc.identity.document_uid}
            // The failure a Temporal child job reported: for a run that died
            // before any stage started, this is the ONLY account of it —
            // `processing.errors` is keyed by stage and stays empty. Already in
            // hand from the task feed, so the Resources tab stops being the one
            // surface that shows "Erreur" with nothing behind it (#2315 put the
            // message on the task; it only ever reached the task popover).
            taskError={docOutcomes.failed.get(row.doc.identity.document_uid)?.error}
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
                  if (value === "relaunch" && currentTag) void relaunchIngestion([row.doc], currentTag.id);
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
    // Rooted inside a library, the trail starts at the library itself: the
    // corpus above it is not somewhere this workspace can go.
    const rootLabel = baseFull ? baseFull.split("/").pop()! : t("rework.resources.roots.resources");
    if (currentFull === baseFull) return [{ label: rootLabel }];
    const relative = baseFull ? currentFull!.slice(baseFull.length + 1) : currentFull!;
    const parts = relative.split("/");
    const segments = [{ label: rootLabel, onClick: () => navigateTo(baseFull) }];
    let acc = baseFull ?? "";
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
  }, [currentFull, baseFull, t, navigateTo]);

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
  const atRoot = currentFull === baseFull;
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
          canGoBack: !atRoot,
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
          hasSelection ? (
            <BulkActionsBar
              selectedCount={selectedDocs.length + selectedFolders.length}
              // Selection survives read-only because bulk download is a read:
              // only the actions that write drop out, so the same rows can
              // still be picked and fetched as a ZIP.
              onDelete={canCreateFolder ? bulkDelete : undefined}
              deleteLoading={bulkDeleting}
              relaunch={
                canCreateFolder && relaunchableSelection.length > 0
                  ? {
                      count: relaunchableSelection.length,
                      onClick: () => void bulkRelaunch(),
                      loading: bulkRelaunching,
                    }
                  : undefined
              }
              onClearSelection={() => setSelectedKeys(new Set())}
              searchToggle={
                // A folder-containing selection can't be resolved to a single
                // direction cheaply (#2446): offer "exclude" only, resolved on
                // click. A file-only selection keeps the directional toggle.
                !canCreateFolder
                  ? undefined
                  : selectedFolders.length > 0
                    ? { mode: "exclude", onClick: () => void bulkExcludeSelection(), loading: bulkExcluding }
                    : searchToggleMode
                      ? { mode: searchToggleMode, onClick: bulkToggleSearchable }
                      : undefined
              }
              onDownload={() => void bulkDownload()}
              downloadLoading={bulkDownloading}
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
              )}
            </>
          )
        }
        loading={tagsLoading}
        loadingMessage={t("rework.resources.loading")}
        empty={isEmpty}
        emptyMessage={
          // "Create a library" belongs to the corpus root alone: an empty
          // library, or an empty folder inside one, is not an invitation to
          // create anything here.
          atRoot && !baseFull ? t("rework.resources.empty.createLibrary") : t("rework.resources.empty.folder")
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
        // Controlled: the server ordered the whole tag before cutting this
        // page, so the table must not re-sort the rows it was handed. And the
        // active header only ever flips direction — clearing would have to fall
        // back to a default column, which reads as the sort jumping elsewhere.
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

      <DocumentPreviewDrawer target={commands.previewTarget} onClose={commands.closePreview} />
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
        parentPath={currentFull ?? undefined}
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
              await commands.renameFolder(renameTarget.node, newName);
            } else {
              await commands.renameDocument(renameTarget.doc, newName, currentTag?.id);
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
