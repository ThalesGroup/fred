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

import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { DocRow } from "@shared/molecules/DocRow/DocRow.tsx";
import { FolderRow } from "@shared/molecules/FolderRow/FolderRow.tsx";
import {
  useDeleteFileMutation,
  useLsQuery,
  useMkdirMutation,
  useUploadFileMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { downloadAuthed } from "../../../../../utils/downloadUtils.tsx";
import { useConfirmationDialog } from "../../../../../components/ConfirmationDialogProvider";
import CreateFolderModal from "../CreateFolderModal/CreateFolderModal.tsx";
import styles from "./TeamFilesystemBrowser.module.css";

/** One entry returned by the /fs/list endpoint (path is the direct child name). */
interface FsEntry {
  path: string;
  size?: number | null;
  type?: string;
  modified?: string | null;
}

const INDENT_STEP = 16;

function isDirectory(type: string | undefined): boolean {
  return typeof type === "string" && type.toLowerCase().includes("directory");
}

function fileExtension(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
}

function sortEntries(entries: FsEntry[]): FsEntry[] {
  return [...entries].sort((a, b) => {
    const dirDelta = Number(isDirectory(b.type)) - Number(isDirectory(a.type));
    return dirDelta !== 0 ? dirDelta : a.path.localeCompare(b.path);
  });
}

/** Authenticated fetch → blob → save (files are proxied through Knowledge Flow). */
async function downloadFsFile(fullPath: string, name: string): Promise<void> {
  await downloadAuthed(`/knowledge-flow/v1/fs/download/${encodeURI(fullPath)}`, name);
}

interface TeamFilesystemBrowserProps {
  /** Team-rooted base path for this area, e.g. `teams/{team}/shared` or `teams/{team}/users/{uid}`. */
  root: string;
}

/**
 * Browse one team-rooted filesystem area (FILES-04) as a collapsible tree, using the same
 * `FolderRow` / `DocRow` molecules as the indexed corpus so both look and behave identically.
 * Folders expand in place; each folder carries upload + new-folder actions; files carry
 * download + delete. Adding at the root is the root header "+" (FsRootAddMenu).
 */
export default function TeamFilesystemBrowser({ root }: TeamFilesystemBrowserProps) {
  const { refetch } = useLsQuery({ path: root });
  return <FsLevel path={root} depth={0} onChanged={() => void refetch()} />;
}

interface FsLevelProps {
  path: string;
  depth: number;
  /** refetch of the directory that owns these entries (so deletes here update the list). */
  onChanged: () => void;
}

/** Renders the entries of one directory; recurses into expanded folders. */
function FsLevel({ path, depth, onChanged }: FsLevelProps) {
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();
  const { data } = useLsQuery({ path });
  const [deleteFile, { isLoading: isDeleting }] = useDeleteFileMutation();

  const entries: FsEntry[] = Array.isArray(data) ? (data as FsEntry[]) : [];

  const handleDelete = async (name: string) => {
    await deleteFile({ path: `${path}/${name}` }).unwrap();
    onChanged();
  };

  const confirmDelete = (name: string) =>
    showConfirmationDialog({
      title: t("rework.resources.confirm.deleteTitle"),
      message: t("rework.resources.confirm.deleteMessage", { name }),
      onConfirm: () => {
        if (!isDeleting) void handleDelete(name);
      },
    });

  return (
    <>
      {sortEntries(entries).map((entry) => {
        const childPath = `${path}/${entry.path}`;
        if (isDirectory(entry.type)) {
          return <FsFolder key={childPath} path={childPath} name={entry.path} depth={depth} onDeleted={onChanged} />;
        }
        return (
          <div key={childPath} className={styles.row} style={{ paddingLeft: depth * INDENT_STEP }}>
            <DocRow
              id={childPath}
              name={entry.path}
              fileType={fileExtension(entry.path)}
              onDownload={() => void downloadFsFile(childPath, entry.path)}
              moreActions={[
                {
                  id: "delete",
                  label: t("rework.resources.action.delete"),
                  onSelect: () => confirmDelete(entry.path),
                },
              ]}
            />
          </div>
        );
      })}
    </>
  );
}

interface FsFolderProps {
  path: string;
  name: string;
  depth: number;
  /** refetch of the directory that owns this folder, so deleting it updates the parent list. */
  onDeleted: () => void;
}

/** One folder row + its lazily-listed children when expanded. Owns upload / new-folder / delete. */
function FsFolder({ path, name, depth, onDeleted }: FsFolderProps) {
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();
  const [expanded, setExpanded] = useState(false);
  const [newFolderOpen, setNewFolderOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const { refetch } = useLsQuery({ path }, { skip: !expanded });
  const [uploadFile] = useUploadFileMutation();
  const [mkdir] = useMkdirMutation();
  const [deleteFolder] = useDeleteFileMutation();

  const reload = () => {
    if (expanded) void refetch();
    else setExpanded(true);
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append("file", file);
      await uploadFile({ path: `${path}/${file.name}`, bodyUploadFile: formData as never }).unwrap();
    }
    reload();
  };

  const handleMkdir = async (folderName: string) => {
    await mkdir({ path: `${path}/${folderName}` }).unwrap();
    reload();
  };

  const confirmDeleteFolder = () =>
    showConfirmationDialog({
      title: t("rework.resources.confirm.deleteTitle"),
      message: t("rework.resources.confirm.deleteMessage", { name }),
      onConfirm: () => {
        void deleteFolder({ path })
          .unwrap()
          .then(() => onDeleted());
      },
    });

  return (
    <>
      <div className={styles.row} style={{ paddingLeft: depth * INDENT_STEP }}>
        <FolderRow
          id={path}
          name={name}
          expanded={expanded}
          onToggle={() => setExpanded((value) => !value)}
          onUpload={() => fileInputRef.current?.click()}
          onCreateSubfolder={() => setNewFolderOpen(true)}
          onDelete={confirmDeleteFolder}
        />
      </div>

      {expanded && <FsLevel path={path} depth={depth + 1} onChanged={() => void refetch()} />}

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
        onCreated={() => reload()}
      />
    </>
  );
}
