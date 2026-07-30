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
import ResourceExplorer from "@shared/organisms/ResourceExplorer/ResourceExplorer.tsx";
import type { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import IconButtonMenu from "@shared/molecules/IconButtonMenu/IconButtonMenu.tsx";
import { Tooltip } from "@shared/atoms/Tooltip/Tooltip.tsx";
import Icon from "@shared/atoms/Icon/Icon.tsx";
import { OriginBadge } from "@shared/atoms/OriginBadge/OriginBadge.tsx";
import type { OptionModel } from "@models/Option.model.ts";
import { useConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  type FilesystemResourceInfoResult,
  useCopyToSharedMutation,
  useDeleteFileMutation,
  useLsQuery,
  useMkdirMutation,
  useRenameMutation,
  useUploadFileMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useUsersByIdsQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { userDisplayName } from "@core/utils/userDisplayName.ts";
import { formatBytes } from "@shared/utils/formatBytes.ts";
import { formatDateTime } from "../../../../utils/formatDateTime.ts";
import { FOLDER_ICON, fileIconSpec } from "../../../../utils/fileIconSpec.ts";
import CreateFolderModal from "../CreateFolderModal/CreateFolderModal.tsx";
import RenameModal from "../RenameModal/RenameModal.tsx";
import BulkActionsBar from "../BulkActionsBar/BulkActionsBar.tsx";
import { downloadAuthed, downloadManyAsZip, fetchAuthedBlob } from "../../../../../utils/downloadUtils.tsx";
import styles from "./FilesystemWorkspace.module.css";

/** Provenance origins we badge on file rows → their i18n label keys. */
const ORIGIN_LABEL_KEY: Record<string, string> = {
  uploaded: "rework.resources.provenance.origins.uploaded",
  agent_generated: "rework.resources.provenance.origins.agent_generated",
  shared_copy: "rework.resources.provenance.origins.shared_copy",
};

/** RFC §4 conventional folder names → localized labels; any other name passes through. */
const CONVENTIONAL_FOLDER_KEY: Record<string, string> = {
  templates: "rework.resources.folders.templates",
  uploads: "rework.resources.folders.uploads",
  outputs: "rework.resources.folders.outputs",
  work: "rework.resources.folders.work",
};

/** Private spaces (Mon espace, an agent's user space) live under `/users/`; only those
 * files can be shared into the team. Files already in Espace d'équipe cannot be re-shared. */
function isShareableArea(path: string): boolean {
  return path.includes("/users/");
}

function fileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
}

/** Authenticated fetch → blob → save (files are proxied through Knowledge Flow). */
async function downloadFsFile(fullPath: string, name: string): Promise<void> {
  await downloadAuthed(`/knowledge-flow/v1/fs/download/${encodeURI(fullPath)}`, name);
}

function sortEntries(entries: FilesystemResourceInfoResult[]): FilesystemResourceInfoResult[] {
  return [...entries].sort((a, b) => {
    const dirDelta = Number(b.type === "directory") - Number(a.type === "directory");
    return dirDelta !== 0 ? dirDelta : a.path.localeCompare(b.path);
  });
}

interface FilesystemWorkspaceProps {
  /** Team-rooted base path for this area, e.g. `teams/{team}/shared` or `teams/{team}/users/{uid}`. */
  root: string;
  /** Breadcrumb's own root segment label — the tab's own name ("Mon espace"/
   * "Espace d'équipe"), since this component is shared by both tabs. */
  rootLabel: string;
  /** Whether upload/new-folder/rename/delete actions are shown. Private areas (Mon
   * espace) are always writable by their owner; only the shared area is gated by
   * CAN_UPDATE_RESOURCES. Defaults to true so existing private-root call sites are
   * unaffected. */
  canWrite?: boolean;
  /** i18n key of the hint shown when the root itself has no entries. */
  emptyHintKey?: string;
  /** Called instead of being a no-op when the user clicks back while already
   * at `root` — lets a host compose this component as one level of a larger
   * virtual hierarchy (Agents: the agent list is the level above every
   * agent's own root). */
  onNavigateAboveRoot?: () => void;
}

/**
 * Browse one team-rooted filesystem area (FILES-04) as a breadcrumb-navigated
 * table — the `/fs` counterpart of `DocumentWorkspace`, built on the same
 * `ResourceExplorer` shell (RFC §13.7 FRONT-09.H). Used directly for "Mon
 * espace"/"Espace d'équipe" (step 2), and mounted by `AgentsWorkspace` for
 * one agent at a time once the user picks an agent from its virtual root
 * (step 3, via `onNavigateAboveRoot`).
 */
export default function FilesystemWorkspace({
  root,
  rootLabel,
  canWrite = true,
  emptyHintKey,
  onNavigateAboveRoot,
}: FilesystemWorkspaceProps) {
  const { t } = useTranslation();
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  const [currentPath, setCurrentPath] = useState(root);
  const [, setNavigationHistory] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [selectedKeys, setSelectedKeys] = useState<ReadonlySet<string | number>>(new Set());
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const [renameTarget, setRenameTarget] = useState<FilesystemResourceInfoResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const navigateTo = useCallback(
    (path: string) => {
      setNavigationHistory((prev) => [...prev, currentPath]);
      setCurrentPath(path);
      setSelectedKeys(new Set());
    },
    [currentPath],
  );

  const navigateBack = useCallback(() => {
    setNavigationHistory((prev) => {
      if (prev.length === 0) {
        // Nothing to pop — either a true no-op (default), or exit to
        // whatever virtual level a host composed this component under.
        onNavigateAboveRoot?.();
        return prev;
      }
      setCurrentPath(prev[prev.length - 1]);
      setSelectedKeys(new Set());
      return prev.slice(0, -1);
    });
  }, [onNavigateAboveRoot]);

  const { data, isLoading, refetch } = useLsQuery({ path: currentPath });
  // `ls`'s response_model isn't generated (LsApiResponse = any) even though
  // the runtime shape matches FilesystemResourceInfoResult exactly — a
  // backend typing gap, not fixed here (same class of workaround the old
  // hand-typed FsEntry duplicate was already relying on).
  const entries = useMemo(
    () => sortEntries((Array.isArray(data) ? data : []) as FilesystemResourceInfoResult[]),
    [data],
  );

  const [uploadFile] = useUploadFileMutation();
  const [mkdir] = useMkdirMutation();
  const [deleteFile] = useDeleteFileMutation();
  const [copyToShared] = useCopyToSharedMutation();
  const [renameFile] = useRenameMutation();

  const filteredEntries = useMemo(() => {
    const trimmed = search.trim().toLowerCase();
    if (!trimmed) return entries;
    return entries.filter((entry) => entry.path.toLowerCase().includes(trimmed));
  }, [entries, search]);

  const selectedEntries = useMemo(
    () => filteredEntries.filter((entry) => selectedKeys.has(entry.path)),
    [filteredEntries, selectedKeys],
  );

  // Batched once for the current level (not one query per row, same #2096
  // pattern as Corpus's Auteur column) — `created_by` is a Keycloak uid.
  const creatorUids = useMemo(
    () => Array.from(new Set(entries.map((entry) => entry.created_by).filter((uid): uid is string => Boolean(uid)))),
    [entries],
  );
  const { data: creators = [] } = useUsersByIdsQuery({ ids: creatorUids }, { skip: creatorUids.length === 0 });
  const creatorById = useMemo(() => new Map(creators.map((summary) => [summary.id, summary])), [creators]);

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    try {
      for (const file of Array.from(files)) {
        const formData = new FormData();
        formData.append("file", file);
        await uploadFile({ path: `${currentPath}/${file.name}`, bodyUploadFile: formData as never }).unwrap();
      }
      void refetch();
    } catch (e: unknown) {
      showError?.({
        summary: t("validation.error"),
        detail: (e as { data?: { detail?: string } })?.data?.detail ?? "Failed to upload.",
      });
    }
  };

  const handleMkdir = async (name: string) => {
    await mkdir({ path: `${currentPath}/${name}` }).unwrap();
    void refetch();
  };

  const confirmDelete = (entry: FilesystemResourceInfoResult) =>
    showConfirmationDialog({
      title: t("rework.resources.confirm.deleteTitle"),
      message: t("rework.resources.confirm.deleteMessage", { name: entry.path }),
      onConfirm: () => {
        void deleteFile({ path: `${currentPath}/${entry.path}` })
          .unwrap()
          .then(() => refetch());
      },
    });

  const bulkDelete = () => {
    if (selectedEntries.length === 0) return;
    showConfirmationDialog({
      title: t("rework.resources.confirm.deleteTitle"),
      message: t("rework.resources.confirm.deleteBulkMessage", { count: selectedEntries.length }),
      onConfirm: () => {
        void Promise.all(
          selectedEntries.map((entry) => deleteFile({ path: `${currentPath}/${entry.path}` }).unwrap()),
        ).then(() => {
          setSelectedKeys(new Set());
          void refetch();
        });
      },
    });
  };

  // Folders are silently skipped (no recursive folder download) — a mixed
  // folder+file selection still zips just the files. Selection is left
  // as-is afterward, unlike bulkDelete: non-destructive and repeatable.
  const [bulkDownloading, setBulkDownloading] = useState(false);
  const bulkDownload = async () => {
    const files = selectedEntries.filter((entry) => entry.type === "file");
    if (files.length === 0) return;
    setBulkDownloading(true);
    try {
      await downloadManyAsZip(
        files.map((entry) => ({
          filename: entry.path,
          fetchBlob: () =>
            fetchAuthedBlob(`/knowledge-flow/v1/fs/download/${encodeURI(`${currentPath}/${entry.path}`)}`),
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

  const confirmShare = (entry: FilesystemResourceInfoResult) =>
    showConfirmationDialog({
      title: t("rework.resources.confirm.shareTitle"),
      message: t("rework.resources.confirm.shareMessage", { name: entry.path }),
      onConfirm: () => void copyToShared({ path: encodeURI(`${currentPath}/${entry.path}`) }).unwrap(),
    });

  const moreOptionsForEntry = (
    entry: FilesystemResourceInfoResult,
  ): OptionModel<"rename" | "download" | "share" | "delete">[] => {
    const options: OptionModel<"rename" | "download" | "share" | "delete">[] = [];
    if (canWrite) {
      options.push({
        value: "rename",
        key: "rename",
        label: t("rework.resources.action.rename"),
        icon: { category: "outlined", type: "drive_file_rename_outline" },
      });
    }
    // Download is read-only — offered regardless of canWrite, unlike the
    // three mutating actions around it.
    if (entry.type === "file") {
      options.push({
        value: "download",
        key: "download",
        label: t("rework.resources.action.download"),
        icon: { category: "outlined", type: "download" },
      });
    }
    if (canWrite && entry.type === "file" && isShareableArea(currentPath)) {
      options.push({
        value: "share",
        key: "share",
        label: t("rework.resources.action.copyToTeam"),
        icon: { category: "outlined", type: "content_copy" },
      });
    }
    if (canWrite) {
      options.push({
        value: "delete",
        key: "delete",
        label: t("rework.resources.action.delete"),
        icon: { category: "outlined", type: "delete" },
        destructive: true,
      });
    }
    return options;
  };

  const columns: DataTableColumn<FilesystemResourceInfoResult>[] = [
    {
      label: t("rework.resources.columns.name"),
      size: "2fr",
      cellRenderer: (entry) => {
        if (entry.type === "directory") {
          const label = CONVENTIONAL_FOLDER_KEY[entry.path] ? t(CONVENTIONAL_FOLDER_KEY[entry.path]) : entry.path;
          return (
            <button
              type="button"
              className={styles.nameButton}
              onClick={() => navigateTo(`${currentPath}/${entry.path}`)}
            >
              <span className={styles.rowIcon} style={{ color: FOLDER_ICON.color }}>
                <Icon category="outlined" type={FOLDER_ICON.type} filled={FOLDER_ICON.filled} />
              </span>
              <span>{label}</span>
            </button>
          );
        }
        const spec = fileIconSpec(fileExtension(entry.path));
        const originLabelKey = entry.origin ? ORIGIN_LABEL_KEY[entry.origin] : undefined;
        return (
          <span className={styles.nameCell}>
            <span className={styles.rowIcon} style={{ color: spec.color }}>
              <Icon category="outlined" type={spec.type} filled={spec.filled} />
            </span>
            <span>{entry.path}</span>
            {entry.origin && originLabelKey && <OriginBadge origin={entry.origin} label={t(originLabelKey)} />}
          </span>
        );
      },
    },
    {
      label: t("rework.resources.columns.size"),
      size: "6.5rem",
      cellRenderer: (entry) => (
        <span className={styles.nowrapCell}>{entry.type === "directory" ? "—" : formatBytes(entry.size ?? 0)}</span>
      ),
    },
    {
      label: t("rework.resources.columns.created"),
      size: "9rem",
      cellRenderer: (entry) => <span className={styles.nowrapCell}>{formatDateTime(entry.created)}</span>,
    },
    {
      label: t("rework.resources.columns.author"),
      size: "9rem",
      cellRenderer: (entry) => {
        const uid = entry.created_by;
        return <span className={styles.nowrapCell}>{uid ? userDisplayName(uid, creatorById.get(uid)) : "—"}</span>;
      },
    },
    {
      label: "",
      size: "4rem",
      cellRenderer: (entry) => (
        <span className={styles.actionsCell}>
          <IconButtonMenu<"rename" | "download" | "share" | "delete">
            iconButton={{
              color: "on-surface-retreat",
              variant: "icon",
              size: "small",
              icon: { category: "outlined", type: "more_vert" },
              "aria-label": t("rework.resources.action.more"),
            }}
            options={moreOptionsForEntry(entry)}
            onSelect={(value) => {
              if (value === "rename") setRenameTarget(entry);
              if (value === "download") void downloadFsFile(`${currentPath}/${entry.path}`, entry.path);
              if (value === "share") confirmShare(entry);
              if (value === "delete") confirmDelete(entry);
            }}
          />
        </span>
      ),
    },
  ];

  const breadcrumbSegments = useMemo(() => {
    const relative = currentPath.slice(root.length).replace(/^\//, "");
    if (!relative) return [{ label: rootLabel, onClick: onNavigateAboveRoot }];
    const segments = [{ label: rootLabel, onClick: () => navigateTo(root) }];
    const parts = relative.split("/");
    let acc = root;
    parts.forEach((part, i) => {
      acc = `${acc}/${part}`;
      const stepPath = acc;
      const isLast = i === parts.length - 1;
      const label = CONVENTIONAL_FOLDER_KEY[part] ? t(CONVENTIONAL_FOLDER_KEY[part]) : part;
      segments.push({ label, onClick: isLast ? undefined : () => navigateTo(stepPath) });
    });
    return segments;
  }, [currentPath, root, rootLabel, t, navigateTo, onNavigateAboveRoot]);

  return (
    <div className={styles.workspace}>
      <ResourceExplorer<FilesystemResourceInfoResult>
        breadcrumb={{
          segments: breadcrumbSegments,
          onBack: navigateBack,
          canGoBack: currentPath !== root || !!onNavigateAboveRoot,
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
          selectedEntries.length > 0 ? (
            <BulkActionsBar
              selectedCount={selectedEntries.length}
              onDelete={bulkDelete}
              onClearSelection={() => setSelectedKeys(new Set())}
              onDownload={
                selectedEntries.some((entry) => entry.type === "file") ? () => void bulkDownload() : undefined
              }
              downloadLoading={bulkDownloading}
            />
          ) : (
            canWrite && (
              <>
                <Tooltip text={t("rework.resources.action.newSubfolder")}>
                  <IconButton
                    color="primary"
                    variant="icon"
                    size="medium"
                    icon={{ category: "outlined", type: "create_new_folder" }}
                    aria-label={t("rework.resources.action.newSubfolder")}
                    onClick={() => setNewFolderOpen(true)}
                  />
                </Tooltip>
                <Tooltip text={t("rework.resources.action.addFile")}>
                  <IconButton
                    color="primary"
                    variant="icon"
                    size="medium"
                    icon={{ category: "outlined", type: "upload_file" }}
                    aria-label={t("rework.resources.action.addFile")}
                    onClick={() => fileInputRef.current?.click()}
                  />
                </Tooltip>
              </>
            )
          )
        }
        loading={isLoading}
        loadingMessage={t("rework.resources.loading")}
        // Unfiltered count, same convention as Corpus's isEmpty: a search
        // with zero matches renders an empty table, not the "this folder
        // has nothing in it" hint (that message would be misleading — the
        // folder isn't empty, the search just doesn't match anything).
        empty={!isLoading && entries.length === 0}
        emptyMessage={t(emptyHintKey ?? "rework.resources.empty.folder")}
        columns={columns}
        rows={filteredEntries}
        rowKey={(entry) => entry.path}
        selectedKeys={selectedKeys}
        onSelectedKeysChange={setSelectedKeys}
      />

      <input
        ref={fileInputRef}
        type="file"
        multiple
        hidden
        onChange={(event) => {
          void handleUpload(event.target.files);
          event.target.value = "";
        }}
      />
      <CreateFolderModal
        open={newFolderOpen}
        onClose={() => setNewFolderOpen(false)}
        onSubmit={handleMkdir}
        onCreated={() => void refetch()}
      />
      {renameTarget && (
        <RenameModal
          open={!!renameTarget}
          onClose={() => setRenameTarget(null)}
          initialName={renameTarget.path}
          onSubmit={async (newName) => {
            try {
              await renameFile({
                path: `${currentPath}/${renameTarget.path}`,
                bodyRename: { new_name: newName },
              }).unwrap();
              showSuccess?.({ summary: t("validation.updated") });
              void refetch();
            } catch (e: unknown) {
              showError?.({
                summary: t("validation.error"),
                detail: (e as { data?: { detail?: string } })?.data?.detail ?? "Failed to rename.",
              });
              throw e;
            }
          }}
        />
      )}
    </div>
  );
}
