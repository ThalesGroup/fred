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
import UnfoldLessIcon from "@mui/icons-material/UnfoldLess";
import UnfoldMoreIcon from "@mui/icons-material/UnfoldMore";
import UploadIcon from "@mui/icons-material/Upload";
import { Box, Breadcrumbs, Button, Card, Chip, IconButton, Link, TextField, Tooltip, Typography } from "@mui/material";
import * as React from "react";
import { useTranslation } from "react-i18next";
import { LibraryCreateDrawer } from "../../../common/LibraryCreateDrawer";
import { useTagCommands } from "../../../common/useTagCommands";
import { usePermissions } from "../../../security/usePermissions";

import {
  DocumentMetadata,
  TagWithItemsId,
  useListAllTagsKnowledgeFlowV1TagsGetQuery,
  useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation,
} from "../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useConfirmationDialog } from "../../ConfirmationDialogProvider";
import { buildTree, findNode, TagNode } from "../../tags/tagTree";
import { useDocumentCommands } from "../common/useDocumentCommands";
import { docHasAnyTag, matchesDocByName } from "./documentHelper";
import { DocumentLibraryTree } from "./DocumentLibraryTree";
import { DocumentUploadDrawer } from "./DocumentUploadDrawer";

export default function DocumentLibraryList() {
  const { t } = useTranslation();
  const { showConfirmationDialog } = useConfirmationDialog();

  /* ---------------- State ---------------- */
  const [expanded, setExpanded] = React.useState<string[]>([]);
  const [selectedFolder, setSelectedFolder] = React.useState<string | null>(null);
  const [isCreateDrawerOpen, setIsCreateDrawerOpen] = React.useState(false);
  const [openUploadDrawer, setOpenUploadDrawer] = React.useState(false);
  const [uploadTargetTagId, setUploadTargetTagId] = React.useState<string | null>(null);
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

  const [fetchAllDocuments, { data: allDocuments = [] }] =
    useSearchDocumentMetadataKnowledgeFlowV1DocumentsMetadataSearchPostMutation();

  React.useEffect(() => {
    fetchAllDocuments({ filters: {} });
  }, [fetchAllDocuments]);

  /* ---------------- Tree building ---------------- */
  const tree = React.useMemo<TagNode | null>(() => (tags ? buildTree(tags) : null), [tags]);

  const getChildren = React.useCallback((n: TagNode) => {
    const arr = Array.from(n.children.values());
    arr.sort((a, b) => a.name.localeCompare(b.name));
    return arr;
  }, []);

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
  const allExpanded = React.useMemo(() => expanded.length > 0, [expanded]);

  /* ---------------- Commands ---------------- */
  const { toggleRetrievable, removeFromLibrary, preview, previewPdf, download } = useDocumentCommands({
    refetchTags: refetch,
    refetchDocs: () => fetchAllDocuments({ filters: {} }),
  });

  /* ---------------- Search ---------------- */
  const filteredDocs = React.useMemo<DocumentMetadata[]>(() => {
    const q = query.trim();
    if (!q) return allDocuments;
    return allDocuments.filter((d) => matchesDocByName(d, q));
  }, [allDocuments, query]);

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
        const docsById = new Map<string, DocumentMetadata>(
          (allDocuments ?? []).map((d) => [d.identity.document_uid, d]),
        );
        for (const [docUid, tag] of entries) {
          const doc = docsById.get(docUid);
          if (!doc) continue;
          // eslint-disable-next-line no-await-in-loop
          await removeFromLibrary(doc, tag);
        }
        setSelectedDocs({});
      },
    });
  }, [selectedDocs, allDocuments, removeFromLibrary, setSelectedDocs, showConfirmationDialog, t]);

  const { confirmDeleteFolder } = useTagCommands({
    refetchTags: refetch,
    refetchDocs: () => fetchAllDocuments({ filters: {} }),
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
      {!isLoading && !isError && tree && (
        <Card
          sx={{
            borderRadius: 3,
            display: "flex",
            flexDirection: "column",
            height: "100%",
            maxHeight: "70vh",
          }}
        >
          {/* Tree header */}
          <Box display="flex" alignItems="center" justifyContent="space-between" px={1} py={0.5} flex="0 0 auto">
            <Typography variant="subtitle2" color="text.secondary">
              {t("documentLibrary.folders")}
            </Typography>
            <Tooltip
              title={allExpanded ? t("documentLibrariesList.collapseAll") : t("documentLibrariesList.expandAll")}
            >
              <IconButton size="small" onClick={() => setAllExpanded(!allExpanded)} disabled={!tree}>
                {allExpanded ? <UnfoldLessIcon fontSize="small" /> : <UnfoldMoreIcon fontSize="small" />}
              </IconButton>
            </Tooltip>
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
              onDownload={download}
              onToggleRetrievable={toggleRetrievable}
              onRemoveFromLibrary={removeOneWithConfirm}
              selectedDocs={selectedDocs}
              setSelectedDocs={setSelectedDocs}
              onDeleteFolder={handleDeleteFolder}
              canDeleteDocument={canDeleteDocument}
              canDeleteFolder={canDeleteFolder}
            />
          </Box>
        </Card>
      )}

      {/* Upload drawer */}
      <DocumentUploadDrawer
        isOpen={openUploadDrawer}
        onClose={() => setOpenUploadDrawer(false)}
        onUploadComplete={async () => {
          await refetch();
          await fetchAllDocuments({ filters: {} });
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
    </Box>
  );
}
