// Copyright Thales 2025
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

import AddIcon from "@mui/icons-material/Add";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import SchemaOutlinedIcon from "@mui/icons-material/SchemaOutlined";
import UnfoldLessIcon from "@mui/icons-material/UnfoldLess";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";
import UploadIcon from "@mui/icons-material/Upload";
import { Box, Breadcrumbs, Button, Card, Chip, IconButton, Link, TextField, Tooltip, Typography } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { LibraryCreateDrawer } from "../../../common/LibraryCreateDrawer";
import { useTagCommands } from "../../../common/useTagCommands";
import { usePermissions } from "../../../security/usePermissions";
import { EmptyState } from "../../EmptyState";

import { useLocalStorageState } from "../../../hooks/useLocalStorageState";
import {
  DocumentMetadata,
  TagWithItemsId,
  useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useListUsersKnowledgeFlowV1UsersGetQuery,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useConfirmationDialog } from "../../ConfirmationDialogProvider";
import { buildTree, findNode, TagNode } from "../../tags/tagTree";
import { useToast } from "../../ToastProvider";
import { useDocumentCommands } from "../common/useDocumentCommands";
import { docHasAnyTag, matchesDocByName } from "./documentHelper";
import { DocumentLibraryTree } from "./DocumentLibraryTree";
import { DocumentUploadDrawer } from "./DocumentUploadDrawer";
import { LibraryPipelineDrawer } from "./LibraryPipelineDrawer";

export default function DocumentLibraryList() {
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();

  /* ---------------- State ---------------- */
  const [expanded, setExpanded] = useLocalStorageState<string[]>("DocumentLibraryList.expanded", []);
  const [selectedFolder, setSelectedFolder] = React.useState<string | null>(null);
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = React.useState(false);
  const [openUploadDrawer, setOpenUploadDrawer] = React.useState(false);
  const [uploadTargetTagId, setUploadTargetTagId] = React.useState<string | null>(null);
  const [isPipelineDrawerOpen, setIsPipelineDrawerOpen] = React.useState(false);
  const [pipelineLibraryTagId, setPipelineLibraryTagId] = React.useState<string | null>(null);
  const [pipelineLibraryLabel, setPipelineLibraryLabel] = React.useState<string | null>(null);
  const [downloadingDocUid, setDownloadingDocUid] = React.useState<string | null>(null);
  // Search + selection (docUid -> tag)
  const [query, setQuery] = React.useState<string>("");
  const [selectedDocs, setSelectedDocs] = React.useState<Record<string, TagWithItemsId>>({});
  const selectedCount = React.useMemo(() => Object.keys(selectedDocs).length, [selectedDocs]);
  const clearSelection = React.useCallback(() => setSelectedDocs({}), []);

  // Permissions (RBAC)
  const { can } = usePermissions();
  const canCreateDocument = can("document", "create");
  const canDeleteDocument = can("document", "delete");
  const canDeleteFolder = can("tag", "delete");
  const canCreateTag = can("tag", "create");
  const { data: users = [] } = useListUsersKnowledgeFlowV1UsersGetQuery();
  const ownerNamesById = React.useMemo(() => {
    const m: Record<string, string> = {};
    users.forEach((u) => {
      const fullName = [u.first_name, u.last_name].filter(Boolean).join(" ").trim();
      const name = fullName || u.username || "";
      if (name) m[u.id] = name;
    });
    return m;
  }, [users]);

  /* ---------------- Data fetching ---------------- */
  const {
    data: tags,
    isLoading,
    isError,
    refetch,
  } = useListAllTagsKnowledgeFlowV1TagsGetQuery(
    { type: "document", limit: 10000, offset: 0 },
    { refetchOnMountOrArgChange: true },
  );

  /* ---------------- Tree building ---------------- */
  const libraryTags = React.useMemo(
    () => tags?.filter((t) => t.name !== "User Assets" && t.path !== "user-assets"),
    [tags],
  );

  const tree = React.useMemo<TagNode | null>(() => (libraryTags ? buildTree(libraryTags) : null), [libraryTags]);
  const hasFolders = Boolean(tree && tree.children.size > 0);

  const getChildren = React.useCallback((n: TagNode) => {
    const arr = Array.from(n.children.values());
    arr.sort((a, b) => a.name.localeCompare(b.name));
    return arr;
  }, []);

  const { showInfo } = useToast();
  const [browseDocumentsByTag] = useBrowseDocumentsByTagKnowledgeFlowV1DocumentsMetadataBrowsePostMutation();

  const PAGE_SIZE = 20;
  const [currentTagId, setCurrentTagId] = React.useState<string | null>(null);
  const [allDocuments, setAllDocuments] = React.useState<DocumentMetadata[]>([]);
  const [totalDocuments, setTotalDocuments] = React.useState<number>(0);
  const [isLoadingPage, setIsLoadingPage] = React.useState(false);
  const [nextOffset, setNextOffset] = React.useState(0);
  const [perTagDocs, setPerTagDocs] = React.useState<Record<string, DocumentMetadata[]>>({});
  const [perTagTotals, setPerTagTotals] = React.useState<Record<string, number>>({});
  const prefetchedTagsRef = React.useRef<Set<string>>(new Set());
  const prefetchingTagsRef = React.useRef<Set<string>>(new Set());
  const documentsByTagId = React.useMemo<Record<string, DocumentMetadata[]>>(() => perTagDocs, [perTagDocs]);

  const loadPage = React.useCallback(
    async (
      tagId: string,
      offset: number,
      append: boolean,
      applyToCurrent: boolean = true,
      limit: number = PAGE_SIZE,
    ) => {
      if (applyToCurrent) setIsLoadingPage(true);
      try {
        const res = await browseDocumentsByTag({
          browseDocumentsByTagRequest: {
            tag_id: tagId,
            offset,
            limit,
          },
        }).unwrap();
        const docs = res.documents || [];

        setPerTagDocs((prev) => {
            const existing = prev[tagId] || [];
            const merged = append ? [...existing, ...docs] : docs;
            return { ...prev, [tagId]: merged };
          });
        setPerTagTotals((prev) => ({ ...prev, [tagId]: res.total || docs.length }));

        if (applyToCurrent && tagId === currentTagId) {
          setAllDocuments((prev) => (append ? [...prev, ...docs] : docs));
          setTotalDocuments(res.total || docs.length);
          setNextOffset(offset + docs.length);
        }
      } finally {
        if (applyToCurrent) setIsLoadingPage(false);
      }
    },
    [browseDocumentsByTag, currentTagId],
  );

  // Load first page when folder changes
  React.useEffect(() => {
    if (!tree || !selectedFolder) return;
    const node = findNode(tree, selectedFolder);
    const tagId = node?.tagsHere?.[0]?.id;
    setCurrentTagId(tagId || null);
    if (tagId) {
      const cachedDocs = perTagDocs[tagId] || [];
      const cachedTotal = perTagTotals[tagId];
      setAllDocuments(cachedDocs);
      setTotalDocuments(cachedTotal ?? cachedDocs.length);
      setNextOffset(cachedDocs.length);
      if (cachedDocs.length === 0) void loadPage(tagId, 0, false, true);
    } else {
      setAllDocuments([]);
      setTotalDocuments(0);
      setNextOffset(0);
    }
  }, [tree, selectedFolder, perTagDocs, perTagTotals, loadPage]);

  const loadMore = React.useCallback(() => {
    if (!currentTagId) return;
    void loadPage(currentTagId, nextOffset, true);
  }, [currentTagId, loadPage, nextOffset]);

  const loadAll = React.useCallback(() => {
    if (!currentTagId) return;
    const remaining = Math.max(totalDocuments - nextOffset, PAGE_SIZE);
    void loadPage(currentTagId, nextOffset, true, true, remaining);
  }, [currentTagId, loadPage, nextOffset, totalDocuments]);

  // Prefetch first page for each tag to populate counters (cap to avoid overload)
  React.useEffect(() => {
    if (!libraryTags) return;
    const MAX_PREFETCH = 50;
    const missing = libraryTags
      .map((t) => t.id)
      .filter((id): id is string => Boolean(id))
      .filter(
        (id) =>
          perTagTotals[id] === undefined &&
          !prefetchedTagsRef.current.has(id) &&
          !prefetchingTagsRef.current.has(id),
      )
      .slice(0, MAX_PREFETCH);

    if (missing.length === 0) return;

    missing.forEach((id) => prefetchingTagsRef.current.add(id));

    const run = async () => {
      for (const tagId of missing) {
        try {
          await loadPage(tagId, 0, false, false);
          prefetchedTagsRef.current.add(tagId);
        } catch (e) {
          console.warn("[DocumentLibraryList] Prefetch failed for tag", tagId, e);
        } finally {
          prefetchingTagsRef.current.delete(tagId);
        }
      }
    };
    void run();
  }, [tags, perTagTotals, loadPage]);

  /* ---------------- Expand/collapse helpers ---------------- */
  const setAllExpanded = (expand: boolean) => {
    if (!tree) return;
    const ids: string[] = [];
    const walk = (n: TagNode) => {
      for (const c of getChildren(n)) {
        ids.push(c.full);
        if (c.children.size) walk(c);
      }
    };
    walk(tree);
    setExpanded(expand ? ids : []);
  };

  // Auto-select first folder when tree loads to avoid empty initial view
  React.useEffect(() => {
    if (selectedFolder || !tree) return;
    const first = getChildren(tree)[0];
    if (first) setSelectedFolder(first.full);
  }, [selectedFolder, tree, getChildren]);

  const handleOpenPipelineDrawer = () => {
    if (!tree || !selectedFolder) return;
    const node = findNode(tree, selectedFolder);
    // Heuristic: first tag at this node represents the library
    const firstTag = node.tagsHere[0];
    if (!firstTag) return;
    setPipelineLibraryTagId(firstTag.id);
    setPipelineLibraryLabel(firstTag.name);
    setIsPipelineDrawerOpen(true);
  };
  const allExpanded = React.useMemo(() => expanded.length > 0, [expanded]);

  /* ---------------- Commands ---------------- */
  const { toggleRetrievable, removeFromLibrary, bulkRemoveFromLibraryForTag, preview, previewPdf, download } = useDocumentCommands({
    refetchTags: refetch,
    refetchDocs: () => (currentTagId ? loadPage(currentTagId, 0, false) : Promise.resolve()),
  });
  const handleDownload = React.useCallback(
    async (doc: DocumentMetadata) => {
      const name = doc.identity.document_name || doc.identity.document_uid;
      setDownloadingDocUid(doc.identity.document_uid);
      showInfo?.({
        summary: t("documentLibrary.downloadStarting") || "Downloading...",
        detail: name,
      });
      try {
        await download(doc);
      } catch {
        // Error toast already handled in useDocumentCommands
      } finally {
        setDownloadingDocUid((current) => (current === doc.identity.document_uid ? null : current));
      }
    },
    [download, showInfo, t],
  );

  /* ---------------- Search ---------------- */
  const filteredDocs = React.useMemo<DocumentMetadata[]>(() => {
    const q = query.trim();
    if (!q) return allDocuments;
    return allDocuments.filter((d) => matchesDocByName(d, q));
  }, [allDocuments, query]);
  const hasMore = React.useMemo(() => allDocuments.length < totalDocuments, [allDocuments.length, totalDocuments]);

  // Auto-expand branches that contain matches (based on filteredDocs)
  React.useEffect(() => {
    if (!tree) return;
    const q = query.trim();
    if (!q) return;

    const nextExpanded = new Set<string>();

    const nodeHasMatch = (n: TagNode): boolean => {
      const hereTagIds = (n.tagsHere ?? []).map((t) => t.id);
      const hereMatch = filteredDocs.some((d) => docHasAnyTag(d, hereTagIds));
      const childMatch = Array.from(n.children.values()).map(nodeHasMatch).some(Boolean);
      const has = hereMatch || childMatch;
      if (has && n.full !== tree.full) nextExpanded.add(n.full);
      return has;
    };

    nodeHasMatch(tree);
    setExpanded(Array.from(nextExpanded));
  }, [tree, query, filteredDocs]);

  /* ---------------- Bulk actions ---------------- */
  // Single-row confirm wrapper (UI-only)
  const removeOneWithConfirm = React.useCallback(
    (doc: DocumentMetadata, tag: TagWithItemsId) => {
      const name = doc.identity.title || doc.identity.document_name || doc.identity.document_uid;
      showConfirmationDialog({
        title: t("documentLibrary.confirmRemoveTitle") || "Remove from library?",
        message:
          t("documentLibrary.confirmRemoveMessage", { doc: name, folder: tag.name }) ||
          `Remove “${name}” from “${tag.name}”? This does not delete the original file.`,
        onConfirm: () => {
          void removeFromLibrary(doc, tag);
        },
      });
    },
    [showConfirmationDialog, removeFromLibrary, t],
  );

  // Your bulk confirm (already good)
  const bulkRemoveFromLibrary = React.useCallback(() => {
    const entries = Object.entries(selectedDocs);
    if (entries.length === 0) return;

    showConfirmationDialog({
      title: t("documentLibrary.confirmBulkRemoveTitle") || "Remove selected?",
      onConfirm: async () => {
        const docsById = new Map<string, DocumentMetadata>((allDocuments ?? []).map((d) => [d.identity.document_uid, d]));
        const docsByTag = new Map<string, { tag: TagWithItemsId; docs: DocumentMetadata[] }>();

        for (const [docUid, tag] of entries) {
          const doc = docsById.get(docUid);
          if (!doc) continue;
          const existing = docsByTag.get(tag.id);
          if (existing) {
            existing.docs.push(doc);
          } else {
            docsByTag.set(tag.id, { tag, docs: [doc] });
          }
        }

        for (const { tag, docs } of docsByTag.values()) {
          // eslint-disable-next-line no-await-in-loop
          await bulkRemoveFromLibraryForTag(docs, tag);
        }

        setSelectedDocs({});
      },
    });
  }, [selectedDocs, allDocuments, bulkRemoveFromLibraryForTag, setSelectedDocs, showConfirmationDialog, t]);

  const { confirmDeleteFolder } = useTagCommands({
    refetchTags: refetch,
    refetchDocs: () => (currentTagId ? loadPage(currentTagId, 0, false) : Promise.resolve()),
  });
  const handleDeleteFolder = React.useCallback(
    (tag: TagWithItemsId) => {
      // Pass the state reset function as the onSuccess callback
      confirmDeleteFolder(tag, () => {
        // This runs only after the user confirms AND the deletion is successful
        setSelectedFolder(null);
      });
    },
    [confirmDeleteFolder, setSelectedFolder],
  );
  return (
    <Box display="flex" flexDirection="column" gap={2}>
      {/* Top toolbar */}
        <Box display="flex" alignItems="center" justifyContent="space-between" gap={2} flexWrap="wrap">
        <Breadcrumbs>
          <Chip
            label={t("documentLibrariesList.documents")}
            icon={<FolderOutlinedIcon />}
            onClick={() => setSelectedFolder(undefined)}
            clickable
            sx={{ fontWeight: 500 }}
          />
          {selectedFolder?.split("/").map((c, i, arr) => (
            <Link key={i} component="button" onClick={() => setSelectedFolder(arr.slice(0, i + 1).join("/"))}>
              {c}
            </Link>
          ))}
        </Breadcrumbs>

        {/* Search */}
        <TextField
          size="small"
          placeholder={t("documentLibrary.searchPlaceholder") || "Search documents…"}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          sx={{ minWidth: 260 }}
        />

        <Box display="flex" gap={1}>
          <Button
            variant="outlined"
            startIcon={<AddIcon />}
            onClick={() => setIsCreateDrawerOpen(true)}
            disabled={!canCreateTag}
            sx={{ borderRadius: "8px" }}
          >
            {t("documentLibrariesList.createLibrary")}
          </Button>
          <Button
            variant="contained"
            startIcon={<UploadIcon />}
            onClick={() => {
              if (!selectedFolder) return;
              const node = findNode(tree, selectedFolder);
              const firstTagId = node?.tagsHere?.[0]?.id;
              if (firstTagId) {
                setUploadTargetTagId(firstTagId);
                setOpenUploadDrawer(true);
              }
            }}
            disabled={!selectedFolder || !canCreateDocument}
            sx={{ borderRadius: "8px" }}
          >
            {t("documentLibrary.uploadInLibrary")}
          </Button>
        </Box>
      </Box>

      {/* Bulk actions */}
      {selectedCount > 0 && (
        <Card sx={{ p: 1, borderRadius: 2, display: "flex", alignItems: "center", gap: 2 }}>
          <Typography variant="body2">
            {selectedCount} {t("documentLibrary.selected") || "selected"}
          </Typography>
          <Button size="small" variant="outlined" onClick={clearSelection}>
            {t("documentLibrary.clearSelection") || "Clear selection"}
          </Button>
          <Button
            size="small"
            variant="contained"
            color="error"
            onClick={bulkRemoveFromLibrary}
            disabled={!canDeleteDocument}
          >
            {t("documentLibrary.bulkRemoveFromLibrary") || "Remove from library"}
          </Button>
        </Card>
      )}

      {/* Loading & Error */}
      {isLoading && (
        <Card sx={{ p: 3, borderRadius: 3 }}>
          <Typography variant="body2">{t("documentLibrary.loadingLibraries")}</Typography>
        </Card>
      )}
      {isError && (
        <Card sx={{ p: 3, borderRadius: 3 }}>
          <Typography color="error">{t("documentLibrary.failedToLoad")}</Typography>
          <Button onClick={() => refetch()} sx={{ mt: 1 }} size="small" variant="outlined">
            {t("dialogs.retry")}
          </Button>
        </Card>
      )}

      {/* Tree */}
      {!isLoading && !isError && tree && hasFolders && (
        <Card
          sx={{
            borderRadius: 3,
            display: "flex",
            flexDirection: "column",
          }}
        >
          {/* Tree header */}
          <Box display="flex" alignItems="center" justifyContent="space-between" px={1} py={0.5} flex="0 0 auto">
            <Typography variant="subtitle2" color="text.secondary">
              {t("documentLibrary.folders")}
            </Typography>
            <Box display="flex" alignItems="center" gap={1}>
              {selectedFolder && (
                <Tooltip title={t("documentLibrary.configurePipeline") || "Configure processing pipeline"}>
                  <span>
                    <IconButton
                      size="small"
                      color="primary"
                      onClick={handleOpenPipelineDrawer}
                      disabled={!tree}
                    >
                      <SchemaOutlinedIcon fontSize="small" />
                    </IconButton>
                  </span>
                </Tooltip>
              )}
              <Tooltip
                title={allExpanded ? t("documentLibrariesList.collapseAll") : t("documentLibrariesList.expandAll")}
              >
                <IconButton size="small" onClick={() => setAllExpanded(!allExpanded)} disabled={!tree}>
                  {allExpanded ? <UnfoldLessIcon fontSize="small" /> : <UnfoldMoreIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            </Box>
          </Box>

          {/* Scrollable tree content */}
          <Box
            px={1}
            pb={1}
            sx={{
              flex: 1,
              minHeight: 0,
              overflowY: "auto",
            }}
          >
            <DocumentLibraryTree
              tree={tree}
              expanded={expanded}
              setExpanded={setExpanded}
              selectedFolder={selectedFolder}
              setSelectedFolder={setSelectedFolder}
              getChildren={getChildren}
              documents={filteredDocs}
              onPreview={preview}
              onPdfPreview={previewPdf}
              onDownload={handleDownload}
              downloadingDocUid={downloadingDocUid}
              onToggleRetrievable={toggleRetrievable}
              onRemoveFromLibrary={removeOneWithConfirm}
              selectedDocs={selectedDocs}
              setSelectedDocs={setSelectedDocs}
              onDeleteFolder={handleDeleteFolder}
              documentsByTagId={documentsByTagId}
            selectedFolderTotal={totalDocuments}
            perTagTotals={perTagTotals}
            hasMore={hasMore}
            onLoadMore={loadMore}
            onLoadAll={loadAll}
            isLoadingMore={isLoadingPage}
            canDeleteDocument={canDeleteDocument}
            canDeleteFolder={canDeleteFolder}
            ownerNamesById={ownerNamesById}
          />
          </Box>
        </Card>
      )}
      {!isLoading && !isError && tree && !hasFolders && (
        <Card
          sx={{
            borderRadius: 3,
            display: "flex",
            flexDirection: "column",
            flex: 1,
          }}
        >
          <EmptyState
            icon={<FolderOutlinedIcon color="disabled" />}
            title={t("documentLibrariesList.emptyFoldersTitle")}
            description={t("documentLibrariesList.emptyFoldersDescription")}
            actionButton={
              canCreateTag
                ? {
                    label: t("documentLibrariesList.emptyFoldersAction"),
                    onClick: () => setIsCreateDrawerOpen(true),
                    startIcon: <AddIcon />,
                    variant: "contained",
                  }
                : undefined
            }
          />
        </Card>
      )}

      {/* Upload drawer */}
      <DocumentUploadDrawer
        isOpen={openUploadDrawer}
        onClose={() => setOpenUploadDrawer(false)}
        onUploadComplete={async () => {
          await refetch();
          if (currentTagId) {
            await loadPage(currentTagId, 0, false);
          }
        }}
        metadata={{ tags: [uploadTargetTagId] }}
      />

      {/* Create-library drawer */}
      <LibraryCreateDrawer
        isOpen={isCreateDrawerOpen}
        onClose={() => setIsCreateDrawerOpen(false)}
        onLibraryCreated={async () => {
          await refetch();
        }}
        mode="document"
        currentPath={selectedFolder}
      />

      {/* Pipeline configuration drawer */}
      <LibraryPipelineDrawer
        isOpen={isPipelineDrawerOpen}
        onClose={() => setIsPipelineDrawerOpen(false)}
        libraryTagId={pipelineLibraryTagId}
        libraryLabel={pipelineLibraryLabel}
      />
    </Box>
  );
}
