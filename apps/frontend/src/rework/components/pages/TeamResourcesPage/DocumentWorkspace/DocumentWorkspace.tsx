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

import { forwardRef, useCallback, useImperativeHandle, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useSelector } from "react-redux";
import { DocRow, type DocRowMoreAction } from "@shared/molecules/DocRow/DocRow.tsx";
import { FolderRow } from "@shared/molecules/FolderRow/FolderRow.tsx";
import { DocumentUploadDrawer } from "@shared/organisms/DocumentUploadDrawer/DocumentUploadDrawer.tsx";
import { useToast } from "@shared/molecules/Toast/ToastProvider";
import {
  type DocumentMetadata,
  type OwnerFilter,
  type TagWithItemsId,
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { buildTree, findNode, type TagNode } from "../../../../../shared/utils/tagTree.ts";
import { selectActiveTasks } from "../../../../features/tasks/taskSlice";
import { useRefetchOnTaskSuccess } from "../../../../features/tasks/useRefetchOnTaskSuccess";
import { useNotifyOnNewTaskTarget } from "../../../../features/tasks/useNotifyOnNewTaskTarget";
import { useDocumentCommands } from "../../../../../components/documents/common/useDocumentCommands";
import { useConfirmationDialog } from "../../../../../components/ConfirmationDialogProvider";
import { useGetTeamQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { useTeamCapabilities } from "@hooks/useTeamCapabilities.ts";
import CreateFolderModal from "../CreateFolderModal/CreateFolderModal.tsx";
import { deriveDocStatus } from "./deriveDocStatus.ts";
import { ResourcePagination } from "./ResourcePagination/ResourcePagination.tsx";
import styles from "./DocumentWorkspace.module.css";

const PAGE_SIZE = 50;
const INDENT_STEP = 16;

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

/**
 * Documents tab of the resources page: a collapsible folder tree (one tag = one
 * folder) with a server-paginated document list per folder, plus CRUD (upload,
 * new folder, reprocess, delete, toggle searchable). Heavy listing stays on the
 * backend — folders lazy-load their first page on expand.
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

  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [selectedDocId, setSelectedDocId] = useState<string | null>(null);
  const [selectedFolderFull, setSelectedFolderFull] = useState<string | null>(null);
  const [perTag, setPerTag] = useState<Record<string, PageState>>({});
  const [uploadOpen, setUploadOpen] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  // undefined => create at the top level; a path => create a subfolder under it.
  const [createParentPath, setCreateParentPath] = useState<string | undefined>(undefined);

  const openCreateFolder = (parentPath: string | undefined) => {
    setCreateParentPath(parentPath);
    setCreateOpen(true);
  };

  useImperativeHandle(
    ref,
    () => ({
      openUpload: () => setUploadOpen(true),
      openNewFolder: () => {
        if (canCreateFolder) openCreateFolder(undefined);
      },
    }),
    [canCreateFolder],
  );

  const [browseDocumentsByTag] = useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();
  const [processDocuments] = useProcessDocumentsKnowledgeFlowV1ProcessDocumentsPostMutation();

  const selectedNode = selectedFolderFull ? findNode(tree, selectedFolderFull) : null;
  const selectedTag = selectedNode?.tagsHere[0] ?? null;

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

  const commands = useDocumentCommands({
    refetchTags,
    refetchDocs: async (tagId?: string) => {
      if (tagId) await loadTagPage(tagId, perTag[tagId]?.offset ?? 0);
    },
  });

  // When an ingestion task finishes, the browse snapshot that backs its row is
  // stale (still "raw") and would need a manual refresh to show "Ready". Reload
  // just the loaded folder page(s) showing that document so its status goes live.
  // The erasure schedule view reuses this same hook (targetType "conversation").
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
  // Fire on first sighting of the task instead (any state, not just succeeded):
  // the document's metadata is already persisted server-side by then, so
  // refreshing now surfaces the row immediately, live-progressing via the
  // existing per-row task wiring in `DocRow`. Every currently loaded folder page
  // is refreshed since the task's target carries no tag id to narrow which one.
  useNotifyOnNewTaskTarget("document", () => {
    void refetchTags();
    for (const [tagId, page] of Object.entries(perTag)) {
      void loadTagPage(tagId, page.offset);
    }
  });

  const toggleFolder = useCallback(
    (node: TagNode) => {
      const tag = node.tagsHere[0];
      setSelectedFolderFull(node.full);
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(node.full)) next.delete(node.full);
        else next.add(node.full);
        return next;
      });
      if (!expanded.has(node.full) && tag && !perTag[tag.id]) void loadTagPage(tag.id, 0);
    },
    [expanded, perTag, loadTagPage],
  );

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

  const moreActionsFor = useCallback(
    (doc: DocumentMetadata, tag: TagNode["tagsHere"][number]): DocRowMoreAction[] => {
      // Both actions below write to the tag/document (toggle-retrievable, delete),
      // gated backend-side by CAN_UPDATE_RESOURCES via TagPermission.UPDATE — same
      // capability as folder creation. Omitting them (rather than showing a
      // guaranteed-403) also lets DocRow hide the "…" button entirely when the
      // resulting list is empty.
      if (!canCreateFolder) return [];
      return [
        {
          id: "searchable",
          label: t("rework.resources.action.searchable"),
          onSelect: () => void commands.toggleRetrievable(doc),
        },
        {
          id: "delete",
          label: t("rework.resources.action.delete"),
          onSelect: () =>
            showConfirmationDialog({
              title: t("rework.resources.confirm.deleteTitle"),
              message: t("rework.resources.confirm.deleteMessage", {
                name: doc.identity.title || doc.identity.document_name,
              }),
              onConfirm: () => void commands.removeFromLibrary(doc, tag as unknown as TagWithItemsId),
            }),
        },
      ];
    },
    [t, commands, showConfirmationDialog, canCreateFolder],
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

  const aggregateFor = useCallback(
    (node: TagNode) => {
      const tag = node.tagsHere[0];
      const ids = tag?.item_ids ?? [];
      const processing = ids.filter((id) => runningDocIds.has(id)).length;
      const loaded = tag ? (perTag[tag.id]?.docs ?? []) : [];
      const failed = loaded.filter((doc) => deriveDocStatus(doc).status === "failed").length;
      return { processing, failed };
    },
    [perTag, runningDocIds],
  );

  const renderNode = (node: TagNode, depth: number): React.ReactNode => {
    const tag = node.tagsHere[0];
    const isExpanded = expanded.has(node.full);
    const page = tag ? perTag[tag.id] : undefined;
    const children = [...node.children.values()].sort((a, b) => a.name.localeCompare(b.name));

    // Files sit one notch deeper than their folder so the nesting reads clearly.
    const docIndent = (depth + 1) * INDENT_STEP + 8;

    return (
      <div key={node.full}>
        <div className={styles.row} style={{ paddingLeft: depth * INDENT_STEP }}>
          <FolderRow
            id={node.full}
            name={node.name}
            docCount={tag?.item_ids?.length ?? 0}
            expanded={isExpanded}
            onToggle={() => toggleFolder(node)}
            aggregate={aggregateFor(node)}
            onUpload={
              tag && canCreateFolder
                ? () => {
                    setSelectedFolderFull(node.full);
                    setUploadOpen(true);
                  }
                : undefined
            }
            onCreateSubfolder={canCreateFolder ? () => openCreateFolder(node.full) : undefined}
          />
        </div>

        {isExpanded && (
          <>
            {children.map((child) => renderNode(child, depth + 1))}
            {tag && (
              <>
                {page?.loading && (
                  <div className={styles.hint} style={{ paddingLeft: docIndent }}>
                    {t("rework.resources.loading")}
                  </div>
                )}
                {page && !page.loading && page.docs.length === 0 && (
                  <div className={styles.hint} style={{ paddingLeft: docIndent }}>
                    {t("rework.resources.empty.folder")}
                  </div>
                )}
                {page?.docs.map((doc) => (
                  <div key={doc.identity.document_uid} className={styles.row} style={{ paddingLeft: docIndent }}>
                    <DocRow
                      id={doc.identity.document_uid}
                      name={doc.identity.document_name || doc.identity.title || doc.identity.document_uid}
                      fileType={doc.file?.file_type ?? "other"}
                      status={deriveDocStatus(doc).status}
                      selected={selectedDocId === doc.identity.document_uid}
                      onSelect={() => setSelectedDocId(doc.identity.document_uid)}
                      onPreview={() => commands.preview(doc)}
                      onDownload={() => void commands.download(doc)}
                      onProcess={canCreateFolder ? () => void reprocess(doc, tag.id) : undefined}
                      moreActions={moreActionsFor(doc, tag)}
                    />
                  </div>
                ))}
                {page && page.total > PAGE_SIZE && (
                  <div style={{ paddingLeft: docIndent }}>
                    <ResourcePagination
                      offset={page.offset}
                      limit={PAGE_SIZE}
                      total={page.total}
                      onPrev={() => void loadTagPage(tag.id, Math.max(0, page.offset - PAGE_SIZE))}
                      onNext={() => void loadTagPage(tag.id, page.offset + PAGE_SIZE)}
                    />
                  </div>
                )}
              </>
            )}
          </>
        )}
      </div>
    );
  };

  const topLevel = [...tree.children.values()].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className={styles.workspace}>
      {tagsLoading ? (
        <div className={styles.hint}>{t("rework.resources.loading")}</div>
      ) : topLevel.length === 0 ? (
        <div className={styles.hint}>{t("rework.resources.empty.createLibrary")}</div>
      ) : (
        <div className={styles.list}>{topLevel.map((node) => renderNode(node, 0))}</div>
      )}

      <DocumentUploadDrawer
        isOpen={uploadOpen}
        onClose={() => setUploadOpen(false)}
        teamId={teamId}
        destinationPath={selectedNode?.full}
        metadata={{ tags: selectedTag ? [selectedTag.id] : [] }}
        onUploadComplete={() => {
          if (selectedTag) void loadTagPage(selectedTag.id, perTag[selectedTag.id]?.offset ?? 0);
          void refetchTags();
        }}
      />
      <CreateFolderModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        parentPath={createParentPath}
        teamId={isPersonalTeam ? undefined : teamId}
        onCreated={() => void refetchTags()}
      />
    </div>
  );
});

export default DocumentWorkspace;
